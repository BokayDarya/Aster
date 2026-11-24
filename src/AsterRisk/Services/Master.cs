using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using AsterRisk.Core;
using AsterRisk.Network;

namespace AsterRisk.Services;

public sealed class Master : IDisposable
{
    private sealed class Job(JobView view, double[]? losses = null)
    {
        public JobView View = view;
        public double[]? Losses = losses;
        public readonly CancellationTokenSource Cancel = new();
        public Task? Run;
    }
    private readonly object gate = new();
    private readonly Dictionary<string, Job> jobs = new();
    private readonly string[] endpoints;
    private readonly SemaphoreSlim[] workerSlots;
    private readonly Store store;
    private bool disposed;

    public Master(string[] workers, string data)
    {
        if (workers.Length is < 1 or > 8 || workers.Distinct().Count() != workers.Length)
            throw new ArgumentException("Задайте от 1 до 8 разных вычислителей.");
        foreach (var endpoint in workers) Wire.Endpoint(endpoint);
        endpoints = workers;
        workerSlots = workers.Select(_ => new SemaphoreSlim(1)).ToArray();
        store = new Store(data);
        try
        {
            foreach (var saved in store.Load())
            {
                var v = saved.Job;
                if (v.Status == "running")
                {
                    v = v with { Status = "interrupted", Error = "Сервер перезапущен до завершения расчёта." };
                    store.Save(new Stored(v, null));
                }
                jobs.Add(v.Id, new Job(v, saved.Losses));
            }
        }
        catch { store.Dispose(); throw; }
    }

    public async Task<object> Handle(Request r, CancellationToken ct)
    {
        switch (r.Command)
        {
            case "ping": return new { role = "master", pid = Environment.ProcessId };
            case "workers":
                return await Task.WhenAll(endpoints.Select(async endpoint =>
                {
                    try { var p = await Wire.Call(endpoint, "ping", new { }, ct, 4);
                        return new { endpoint, online = true, info = p.Data, error = (string?)null }; }
                    catch (Exception e) when (e is IOException or System.Net.Sockets.SocketException
                        or OperationCanceledException or InvalidOperationException)
                    { return new { endpoint, online = false, info = Json.Element(new { }), error = (string?)e.Message }; }
                }));
            case "submit": return Start(Json.Parse<Submit>(r.Data));
            case "history": lock (gate) return jobs.Values.Select(x => x.View with
                { Result = x.View.Result is null ? null : x.View.Result with { Samples = [], Histogram = [] } })
                .OrderByDescending(x => x.Created).ToArray();
            case "job": lock (gate) return Find(Id(r)).View;
            case "cancel":
                lock (gate) { var j = Find(Id(r)); j.Cancel.Cancel(); return j.View; }
            case "delete":
                lock (gate)
                {
                    string id = Id(r); var j = Find(id);
                    if (j.View.Status == "running") throw new InvalidOperationException("Сначала отмените расчёт.");
                    store.Delete(id); jobs.Remove(id); j.Cancel.Dispose(); return new { deleted = id };
                }
            case "losses":
                lock (gate)
                {
                    var j = Find(Id(r));
                    if (j.View.Status != "completed" || j.Losses == null) throw new InvalidOperationException("Результат не завершён.");
                    var d = r.Data;
                    int offset = d.TryGetProperty("offset", out var o) ? o.GetInt32() : 0;
                    if (offset < 0 || offset >= j.Losses.Length) throw new ArgumentException("Некорректное смещение.");
                    return new { values = j.Losses.Skip(offset).Take(5000).ToArray(), total = j.Losses.Length };
                }
            default: throw new ArgumentException("Неизвестная команда сервера.");
        }
    }

    private static string Id(Request r) => r.Data.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String
        ? id.GetString()! : throw new ArgumentException("ID обязателен.");
    private Job Find(string id) => jobs.TryGetValue(id, out var j) ? j
        : throw new ArgumentException("Расчёт не найден.");

    private JobView Start(Submit submit)
    {
        Validation.Validate(submit.Simulation);
        if (!Guid.TryParse(submit.RequestId, out var requestId)) throw new ArgumentException("RequestId должен быть UUID.");
        submit = submit with { RequestId = requestId.ToString("D") };
        lock (gate)
        {
            var existing = jobs.Values.FirstOrDefault(j => j.View.RequestId == submit.RequestId);
            if (existing != null)
            {
                var a = JsonSerializer.Serialize(submit.Simulation, Json.Options);
                var b = JsonSerializer.Serialize(existing.View.Simulation, Json.Options);
                if (a != b) throw new ArgumentException("Повтор RequestId с другими параметрами.");
                return existing.View;
            }
            if (disposed) throw new InvalidOperationException("Сервер завершает работу.");
            if (jobs.Count >= 20) throw new InvalidOperationException("История заполнена (20). Удалите ненужный расчёт.");
            if (jobs.Values.Count(j => j.View.Status == "running") >= 2)
                throw new InvalidOperationException("Одновременно допускается два расчёта.");
            var view = new JobView(Guid.NewGuid().ToString("N"), submit.RequestId, "running", 0,
                submit.Simulation.Paths, null, null, submit.Simulation, DateTimeOffset.UtcNow);
            var job = new Job(view);
            job.Cancel.CancelAfter(TimeSpan.FromMinutes(10));
            store.Save(new Stored(view, null));
            jobs.Add(view.Id, job);
            job.Run = Task.Run(() => Calculate(job));
            return view;
        }
    }

    private async Task Calculate(Job job)
    {
        var sw = Stopwatch.StartNew();
        var s = job.View.Simulation;
        var losses = new double[s.Paths];
        var samples = new List<Sample>();
        var batches = new int[endpoints.Length];
        var paths = new int[endpoints.Length];
        var failures = new int[endpoints.Length];
        var completed = new bool[(s.Paths + 4999) / 5000];
        try
        {
            await Task.WhenAll(Enumerable.Range(0, completed.Length).Select(async batchIndex =>
            {
                int start = batchIndex * 5000, count = Math.Min(5000, s.Paths - start);
                string? last = null;
                for (int attempt = 0; attempt < endpoints.Length; attempt++)
                {
                    int w = (batchIndex + attempt) % endpoints.Length;
                    await workerSlots[w].WaitAsync(job.Cancel.Token);
                    try
                    {
                        var reply = await Wire.Call(endpoints[w], "calculate", new Batch(s, start, count), job.Cancel.Token);
                        var result = Json.Parse<BatchResult>(reply.Data);
                        double initial = s.Assets.Sum(a => a.Price * a.Quantity);
                        if (result.Start != start || result.Losses.Length != count
                            || result.Losses.Any(x => !double.IsFinite(x) || x > initial + 1e-6)
                            || result.Samples.Length != Math.Min(count, Math.Max(0, 64 - start))
                            || result.Samples.Where((v, i) => v.Index != start + i || v.Values.Length != s.Steps + 1
                                || v.Values.Any(x => !double.IsFinite(x) || x < 0)).Any())
                            throw new InvalidDataException("Повреждённая партия результатов.");
                        lock (gate)
                        {
                            Array.Copy(result.Losses, 0, losses, start, count);
                            samples.AddRange(result.Samples);
                            completed[batchIndex] = true;
                            batches[w]++; paths[w] += count;
                            job.View = job.View with { Completed = job.View.Completed + count };
                        }
                        return;
                    }
                    catch (Exception e) when (e is IOException or System.Net.Sockets.SocketException
                        or OperationCanceledException or InvalidOperationException or JsonException or ArgumentException)
                    { job.Cancel.Token.ThrowIfCancellationRequested(); Interlocked.Increment(ref failures[w]); last = e.Message; }
                    finally { workerSlots[w].Release(); }
                }
                throw new IOException($"Партия {batchIndex} не рассчитана: {last}");
            }));
            job.Cancel.Token.ThrowIfCancellationRequested();
            if (completed.Any(x => !x)) throw new IOException("Получены не все партии.");
            var workerRuns = endpoints.Select((e, i) => new WorkerRun(e, batches[i], paths[i], failures[i])).ToArray();
            var summary = Engine.Aggregate(s, losses, samples.ToArray(), workerRuns, sw.Elapsed.TotalSeconds);
            lock (gate)
            {
                var view = job.View with { Status = "completed", Result = summary };
                store.Save(new Stored(view, losses)); // Успех объявляется только после надёжного сохранения.
                job.Losses = losses; job.View = view;
            }
        }
        catch (Exception e)
        {
            lock (gate)
            {
                var view = job.View with { Status = job.Cancel.IsCancellationRequested ? "cancelled" : "failed",
                    Error = job.Cancel.IsCancellationRequested ? "Расчёт отменён либо превышен общий срок 10 минут." : e.Message, Result = null };
                try { store.Save(new Stored(view, null)); }
                catch (IOException saveError) { view = view with { Error = view.Error + " Ошибка сохранения: " + saveError.Message }; }
                job.View = view;
            }
        }
    }

    public void Dispose()
    {
        Task[] running;
        lock (gate) { disposed = true; foreach (var j in jobs.Values) j.Cancel.Cancel();
            running = jobs.Values.Where(j => j.Run != null).Select(j => j.Run!).ToArray(); }
        Task.WhenAll(running).GetAwaiter().GetResult();
        store.Dispose();
        foreach (var j in jobs.Values) j.Cancel.Dispose();
        foreach (var slot in workerSlots) slot.Dispose();
    }
}
