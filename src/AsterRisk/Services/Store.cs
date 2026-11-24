using System.Security.Cryptography;
using System.Text.Json;
using AsterRisk.Core;

namespace AsterRisk.Services;

public sealed record Stored(JobView Job, double[]? Losses);
public sealed record CheckedFile(string Sha256, JsonElement Content);

public sealed class Store : IDisposable
{
    private readonly string directory;
    private readonly FileStream lease;
    private readonly object gate = new();
    public Store(string path)
    {
        directory = Path.GetFullPath(path);
        Directory.CreateDirectory(directory);
        lease = new FileStream(Path.Combine(directory, "master.lock"), FileMode.OpenOrCreate,
            FileAccess.ReadWrite, FileShare.None);
    }
    public List<Stored> Load()
    {
        var result = new List<Stored>();
        foreach (string path in Directory.GetFiles(directory, "*.json"))
        {
            byte[] bytes = File.ReadAllBytes(path);
            if (bytes.Length > 20 * 1024 * 1024) throw new InvalidDataException($"Архив слишком велик: {path}");
            var file = JsonSerializer.Deserialize<CheckedFile>(bytes, Json.Options)
                ?? throw new InvalidDataException($"Пустой архив: {path}");
            var actual = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(file.Content, Json.Options)));
            if (actual != file.Sha256) throw new InvalidDataException($"Повреждение контрольной суммы: {path}");
            var stored = Json.Parse<Stored>(file.Content);
            if (!Guid.TryParseExact(stored.Job.Id, "N", out _) || !Guid.TryParse(stored.Job.RequestId, out _)
                || Path.GetFileNameWithoutExtension(path) != stored.Job.Id
                || stored.Job.Status is not ("running" or "completed" or "failed" or "cancelled" or "interrupted"))
                throw new InvalidDataException($"Некорректная структура архива: {path}");
            Validation.Validate(stored.Job.Simulation);
            if (stored.Job.Status == "completed" && (stored.Losses?.Length != stored.Job.Total
                || stored.Losses.Any(x => !double.IsFinite(x)) || stored.Job.Result == null))
                throw new InvalidDataException($"Неполные результаты: {path}");
            result.Add(stored);
        }
        if (result.Count > 20) throw new InvalidDataException("История превышает лимит 20 расчётов.");
        return result;
    }
    public void Save(Stored stored)
    {
        var content = Json.Element(stored);
        string hash = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(content, Json.Options)));
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(new CheckedFile(hash, content), Json.Options);
        lock (gate)
        {
            string path = Path.Combine(directory, stored.Job.Id + ".json");
            string temp = path + ".tmp";
            using (var stream = new FileStream(temp, FileMode.Create, FileAccess.Write, FileShare.None))
            { stream.Write(bytes); stream.Flush(true); }
            File.Move(temp, path, true);
        }
    }
    public void Delete(string id)
    {
        if (!Guid.TryParseExact(id, "N", out _)) throw new ArgumentException("Некорректный ID.");
        lock (gate) File.Delete(Path.Combine(directory, id + ".json"));
    }
    public void Dispose() => lease.Dispose();
}
