using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Text.Json;
using AsterRisk.Core;

namespace AsterRisk.Network;

public sealed record Request(int Version, string Key, string Id, string Command, JsonElement Data);
public sealed record Reply(int Version, string Id, bool Ok, JsonElement Data, string? Error = null);

public static class Wire
{
    public const int Maximum = 4 * 1024 * 1024;
    public static string Key => Environment.GetEnvironmentVariable("ASTER_KEY") ?? "aster-local-course-demo-2026";

    public static async Task<T> Read<T>(Stream stream, CancellationToken ct)
    {
        byte[] header = new byte[4];
        await stream.ReadExactlyAsync(header, ct);
        int length = BinaryPrimitives.ReadInt32BigEndian(header);
        if (length is < 1 or > Maximum) throw new InvalidDataException("Недопустимая длина кадра.");
        byte[] bytes = new byte[length];
        await stream.ReadExactlyAsync(bytes, ct);
        CheckJson(bytes);
        return JsonSerializer.Deserialize<T>(bytes, Json.Options)
            ?? throw new InvalidDataException("Пустой кадр.");
    }

    public static void CheckJson(byte[] bytes)
    {
        var reader = new Utf8JsonReader(bytes, new JsonReaderOptions { MaxDepth = 32 });
        var objects = new Stack<HashSet<string>>();
        while (reader.Read())
        {
            if (reader.TokenType == JsonTokenType.StartObject) objects.Push(new(StringComparer.Ordinal));
            else if (reader.TokenType == JsonTokenType.EndObject) objects.Pop();
            else if (reader.TokenType == JsonTokenType.PropertyName && !objects.Peek().Add(reader.GetString()!))
                throw new InvalidDataException("Повторяющееся имя поля JSON.");
        }
    }

    public static async Task Write<T>(Stream stream, T value, CancellationToken ct)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Json.Options);
        if (bytes.Length > Maximum) throw new InvalidDataException("Ответ превышает размер кадра.");
        byte[] header = new byte[4];
        BinaryPrimitives.WriteInt32BigEndian(header, bytes.Length);
        await stream.WriteAsync(header, ct);
        await stream.WriteAsync(bytes, ct);
    }

    public static (string Host, int Port) Endpoint(string value)
    {
        int split = value.LastIndexOf(':');
        if (split <= 0 || !int.TryParse(value[(split + 1)..], out int port) || port is < 1 or > 65535)
            throw new ArgumentException("Адрес должен иметь вид host:port.");
        return (value[..split], port);
    }

    public static async Task<Reply> Call(string endpoint, string command, object data,
        CancellationToken ct, int seconds = 120)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        var (host, port) = Endpoint(endpoint);
        using var client = new TcpClient { NoDelay = true };
        using (var connect = CancellationTokenSource.CreateLinkedTokenSource(deadline.Token))
        {
            connect.CancelAfter(TimeSpan.FromSeconds(3));
            await client.ConnectAsync(host, port, connect.Token);
        }
        var stream = client.GetStream();
        string id = Guid.NewGuid().ToString("N");
        await Write(stream, new Request(1, Key, id, command, Json.Element(data)), deadline.Token);
        var reply = await Read<Reply>(stream, deadline.Token);
        if (reply.Version != 1 || reply.Id != id) throw new InvalidDataException("Несогласованный ответ.");
        if (!reply.Ok) throw new InvalidOperationException(reply.Error ?? "Ошибка сервера.");
        return reply;
    }

    public static async Task Listen(string endpoint, Func<Request, CancellationToken, Task<object>> handler,
        CancellationToken ct, int capacity = 32)
    {
        var (host, port) = Endpoint(endpoint);
        var ip = IPAddress.Parse(host);
        if (!IPAddress.IsLoopback(ip) && (Key == "aster-local-course-demo-2026" || Key.Length < 24))
            throw new ArgumentException("Для сетевого режима задайте собственный ASTER_KEY.");
        var listener = new TcpListener(ip, port);
        using var slots = new SemaphoreSlim(capacity);
        var tasks = new HashSet<Task>();
        listener.Start(64);
        Console.WriteLine($"TCP {endpoint}; pid={Environment.ProcessId}");
        try
        {
            while (!ct.IsCancellationRequested)
            {
                var client = await listener.AcceptTcpClientAsync(ct);
                if (!slots.Wait(0)) { client.Dispose(); continue; }
                var task = Serve(client);
                lock (tasks) { tasks.RemoveWhere(t => t.IsCompleted); tasks.Add(task); }
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { }
        finally
        {
            listener.Stop();
            Task[] pending;
            lock (tasks) pending = tasks.ToArray();
            await Task.WhenAll(pending);
        }

        async Task Serve(TcpClient client)
        {
            using (client)
            using (var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct))
            {
                deadline.CancelAfter(TimeSpan.FromSeconds(130));
                string id = "unknown";
                try
                {
                    var stream = client.GetStream();
                    using var readDeadline = CancellationTokenSource.CreateLinkedTokenSource(deadline.Token);
                    readDeadline.CancelAfter(TimeSpan.FromSeconds(5));
                    var request = await Read<Request>(stream, readDeadline.Token);
                    id = request.Id;
                    if (request.Version != 1 || request.Key != Key) throw new ArgumentException("Версия или ключ доступа неверны.");
                    if (string.IsNullOrEmpty(id) || id.Length > 64) throw new ArgumentException("Некорректный ID запроса.");
                    var result = await handler(request, deadline.Token);
                    await Write(stream, new Reply(1, id, true, Json.Element(result)), deadline.Token);
                }
                catch (Exception e) when (e is ArgumentException or InvalidDataException or JsonException
                    or InvalidOperationException or IOException or OperationCanceledException or ArithmeticException
                    or KeyNotFoundException or FormatException)
                {
                    try
                    {
                        using var errorDeadline = new CancellationTokenSource(TimeSpan.FromSeconds(1));
                        await Write(client.GetStream(), new Reply(1, id, false, Json.Element(new { }),
                            e is OperationCanceledException ? "Превышен таймаут операции." : e.Message), errorDeadline.Token);
                    }
                    catch (Exception x) when (x is IOException or OperationCanceledException or InvalidOperationException) { }
                }
                finally { slots.Release(); }
            }
        }
    }
}
