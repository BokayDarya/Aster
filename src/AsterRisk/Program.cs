using System.Diagnostics;
using System.Text;
using System.Text.Json;
using AsterRisk.Core;
using AsterRisk.Network;
using AsterRisk.Services;

Console.OutputEncoding = Encoding.UTF8;
var options = new Dictionary<string, string>();
string mode = args.Length > 0 ? args[0] : "demo";
for (int i = 1; i < args.Length; i += 2)
{
    if (!args[i].StartsWith("--") || i + 1 >= args.Length) throw new ArgumentException("Параметры: --имя значение.");
    options.Add(args[i][2..], args[i + 1]);
}
string Get(string key, string fallback) => options.GetValueOrDefault(key, fallback);
using var stop = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; stop.Cancel(); };
try
{
    switch (mode)
    {
        case "worker":
            int threads = int.Parse(Get("threads", "2"));
            if (threads is < 1 or > 16) throw new ArgumentException("Потоки: 1–16.");
            var worker = new Worker(threads);
            await Wire.Listen(Get("listen", "127.0.0.1:7401"), worker.Handle, stop.Token);
            break;
        case "master":
            using (var master = new Master(Get("workers", "127.0.0.1:7401,127.0.0.1:7402").Split(','), Get("data", "data")))
                await Wire.Listen(Get("listen", "127.0.0.1:7400"), master.Handle, stop.Token);
            break;
        case "web":
            await Gateway.Run(Get("url", "http://127.0.0.1:8093/"), Get("master", "127.0.0.1:7400"), stop.Token);
            break;
        case "demo":
            var children = new List<Process>();
            string logDir = Path.GetFullPath(Get("logs", "runtime/logs"));
            Directory.CreateDirectory(logDir);
            try
            {
                Spawn("worker", "--listen", "127.0.0.1:7401", "--threads", Get("threads", "2"));
                Spawn("worker", "--listen", "127.0.0.1:7402", "--threads", Get("threads", "2"));
                Spawn("master", "--data", Path.GetFullPath(Get("data", "data")));
                for (int attempt = 0; attempt < 50; attempt++)
                {
                    if (children.Any(p => p.HasExited)) throw new InvalidOperationException("Процесс не запустился. См. runtime/logs.");
                    try { await Wire.Call("127.0.0.1:7400", "ping", new { }, stop.Token, 2); break; }
                    catch (System.Net.Sockets.SocketException) { await Task.Delay(100, stop.Token); }
                }
                Console.WriteLine("Откройте http://127.0.0.1:8093/ — для завершения нажмите Ctrl+C.");
                await Gateway.Run("http://127.0.0.1:8093/", "127.0.0.1:7400", stop.Token);
            }
            finally
            {
                foreach (var p in children)
                {
                    if (!p.HasExited) { p.Kill(true); await p.WaitForExitAsync(); }
                    p.Dispose();
                }
            }
            void Spawn(params string[] arguments)
            {
                var info = new ProcessStartInfo("dotnet") { UseShellExecute = false,
                    CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
                info.ArgumentList.Add(typeof(Engine).Assembly.Location);
                foreach (var a in arguments) info.ArgumentList.Add(a);
                var p = Process.Start(info) ?? throw new IOException("Не удалось запустить процесс.");
                string log = Path.Combine(logDir, arguments[0] + "-" + p.Id + ".log");
                var logGate = new object();
                p.OutputDataReceived += (_, e) => { if (e.Data != null) lock (logGate) File.AppendAllText(log, e.Data + "\n"); };
                p.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (logGate) File.AppendAllText(log, e.Data + "\n"); };
                p.BeginOutputReadLine(); p.BeginErrorReadLine(); children.Add(p);
            }
            break;
        case "calculate":
            var s = JsonSerializer.Deserialize<Simulation>(await File.ReadAllTextAsync(Get("input", "examples/portfolio.json")), Json.Options)
                ?? throw new ArgumentException("Пустой портфель.");
            var batch = Engine.Calculate(new Batch(s, 0, Math.Min(s.Paths, 5000)), 1, stop.Token);
            Console.WriteLine(JsonSerializer.Serialize(batch, Json.Options));
            break;
        default: throw new ArgumentException("Режимы: demo, master, worker, web, calculate.");
    }
}
catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
catch (Exception e) { Console.Error.WriteLine(e.Message); Environment.ExitCode = 1; }
