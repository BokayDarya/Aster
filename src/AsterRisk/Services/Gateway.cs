using System.Globalization;
using System.Net;
using System.Text;
using System.Text.Json;
using AsterRisk.Core;
using AsterRisk.Network;

namespace AsterRisk.Services;

public static class Gateway
{
    public static async Task Run(string prefix, string master, CancellationToken ct)
    {
        using var listener = new HttpListener();
        listener.Prefixes.Add(prefix);
        listener.Start();
        using var slots = new SemaphoreSlim(16);
        using var stop = ct.Register(listener.Stop);
        var tasks = new HashSet<Task>();
        Console.WriteLine($"ASTER UI {prefix}; pid={Environment.ProcessId}");
        try
        {
            while (!ct.IsCancellationRequested)
            {
                var context = await listener.GetContextAsync();
                if (!slots.Wait(0)) { context.Response.StatusCode = 503; context.Response.Close(); continue; }
                var task = Serve(context);
                lock (tasks) { tasks.RemoveWhere(t => t.IsCompleted); tasks.Add(task); }
            }
        }
        catch (Exception e) when (ct.IsCancellationRequested && e is HttpListenerException or ObjectDisposedException) { }
        finally { Task[] pending; lock (tasks) pending = tasks.ToArray(); await Task.WhenAll(pending); }

        async Task Serve(HttpListenerContext c)
        {
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
            deadline.CancelAfter(TimeSpan.FromSeconds(30));
            var response = c.Response;
            try
            {
                response.Headers["X-Content-Type-Options"] = "nosniff";
                response.Headers["Cache-Control"] = "no-store";
                response.Headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'";
                string path = c.Request.Url!.AbsolutePath;
                if (!path.StartsWith("/api/", StringComparison.Ordinal))
                {
                    if (c.Request.HttpMethod != "GET") throw new ArgumentException("Метод не поддерживается.");
                    string file = path switch { "/" => "index.html", "/app.js" => "app.js", "/style.css" => "style.css", _ => "" };
                    if (file == "") { response.StatusCode = 404; return; }
                    string full = Path.Combine(AppContext.BaseDirectory, "wwwroot", file);
                    response.ContentType = file.EndsWith(".js") ? "text/javascript; charset=utf-8"
                        : file.EndsWith(".css") ? "text/css; charset=utf-8" : "text/html; charset=utf-8";
                    await response.OutputStream.WriteAsync(await File.ReadAllBytesAsync(full, deadline.Token), deadline.Token);
                    return;
                }
                string? origin = c.Request.Headers["Origin"];
                // Host сохраняет внешний порт при перенаправлении порта Docker.
                // Url может содержать внутренний порт слушателя контейнера.
                string requestAuthority = c.Request.Url.Scheme + "://" + c.Request.UserHostName;
                if (origin != null && origin != requestAuthority)
                    throw new ArgumentException("Запрос с другого источника запрещён.");
                if (c.Request.HttpMethod == "POST")
                {
                    if (c.Request.Headers["X-Aster"] != "1") throw new ArgumentException("Отсутствует заголовок X-Aster.");
                    if (c.Request.ContentLength64 is < 1 or > 1024 * 1024
                        || c.Request.ContentType?.Split(';')[0] != "application/json")
                        throw new ArgumentException("Требуется JSON размером до 1 МБ.");
                    byte[] body = new byte[(int)c.Request.ContentLength64];
                    await c.Request.InputStream.ReadExactlyAsync(body, deadline.Token);
                    Wire.CheckJson(body);
                    using var d = JsonDocument.Parse(body);
                    string command = path switch
                    { "/api/submit" => "submit", "/api/cancel" => "cancel", "/api/delete" => "delete", _ => "" };
                    if (command == "") throw new ArgumentException("Маршрут не найден.");
                    var reply = await Wire.Call(master, command, d.RootElement, deadline.Token, 20);
                    await Send(reply.Data);
                }
                else if (c.Request.HttpMethod == "GET")
                {
                    if (path == "/api/workers" || path == "/api/history")
                    {
                        var reply = await Wire.Call(master, path[5..], new { }, deadline.Token, 15);
                        await Send(reply.Data);
                    }
                    else if (path.StartsWith("/api/job/", StringComparison.Ordinal))
                    { var reply = await Wire.Call(master, "job", new { id = path[9..] }, deadline.Token, 10); await Send(reply.Data); }
                    else if (path.StartsWith("/api/export/", StringComparison.Ordinal))
                    {
                        string id = path[12..];
                        if (!Guid.TryParseExact(id, "N", out _)) throw new ArgumentException("Некорректный ID.");
                        var reply = await Wire.Call(master, "job", new { id }, deadline.Token, 10);
                        var job = Json.Parse<JobView>(reply.Data);
                        if (job.Status != "completed") throw new InvalidOperationException("Расчёт не завершён.");
                        bool csv = c.Request.QueryString["format"] == "csv";
                        response.Headers["Content-Disposition"] = $"attachment; filename=aster-{id}.{(csv ? "csv" : "json")}";
                        if (!csv) await Send(reply.Data);
                        else
                        {
                            response.ContentType = "text/csv; charset=utf-8";
                            using var writer = new StreamWriter(response.OutputStream, new UTF8Encoding(true), leaveOpen: true);
                            await writer.WriteLineAsync("rank,loss_" + job.Simulation.Currency);
                            for (int offset = 0; offset < job.Total; offset += 5000)
                            {
                                var chunk = await Wire.Call(master, "losses", new { id, offset }, deadline.Token, 10);
                                int rank = offset;
                                foreach (var v in chunk.Data.GetProperty("values").EnumerateArray())
                                    await writer.WriteLineAsync($"{++rank},{v.GetDouble().ToString("R", CultureInfo.InvariantCulture)}");
                            }
                            await writer.FlushAsync(deadline.Token);
                        }
                    }
                    else { response.StatusCode = 404; }
                }
                else response.StatusCode = 405;
            }
            catch (Exception e) when (e is ArgumentException or InvalidDataException or JsonException
                or InvalidOperationException or IOException or System.Net.Sockets.SocketException
                or OperationCanceledException or KeyNotFoundException)
            {
                try
                {
                    response.StatusCode = e is ArgumentException or JsonException ? 400 : 503;
                    await Send(Json.Element(new { error = e is OperationCanceledException ? "Таймаут соединения." : e.Message }));
                }
                catch (Exception x) when (x is IOException or HttpListenerException or ObjectDisposedException or OperationCanceledException) { }
            }
            finally { response.Close(); slots.Release(); }

            async Task Send(JsonElement element)
            {
                response.ContentType = "application/json; charset=utf-8";
                await response.OutputStream.WriteAsync(JsonSerializer.SerializeToUtf8Bytes(element, Json.Options), deadline.Token);
            }
        }
    }
}
