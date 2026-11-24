using AsterRisk.Core;
using AsterRisk.Network;

namespace AsterRisk.Services;

public sealed class Worker(int threads)
{
    private readonly SemaphoreSlim compute = new(1);
    public async Task<object> Handle(Request r, CancellationToken ct)
    {
        if (r.Command == "ping") return new { pid = Environment.ProcessId, threads, role = "worker" };
        if (r.Command != "calculate") throw new ArgumentException("Неизвестная команда вычислителя.");
        var batch = Json.Parse<Batch>(r.Data);
        if (!await compute.WaitAsync(0, ct)) throw new InvalidOperationException("Вычислитель занят.");
        try { return await Task.Run(() => Engine.Calculate(batch, threads, ct), ct); }
        finally { compute.Release(); }
    }
}
