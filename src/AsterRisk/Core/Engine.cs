namespace AsterRisk.Core;

// Отдельный поток SplitMix64 для каждого абсолютного номера траектории.
// Результат не зависит от числа вычислителей, потоков или повторного назначения партии.
public struct Generator(ulong seed)
{
    private ulong state = seed;
    public ulong Next()
    {
        ulong z = (state += 0x9E3779B97F4A7C15UL);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
        return z ^ (z >> 31);
    }
    public double Uniform() => ((Next() >> 11) + .5) / 9007199254740992.0;
    public double Normal() => Math.Sqrt(-2 * Math.Log(Uniform())) * Math.Cos(2 * Math.PI * Uniform());
}

public static class Engine
{
    public static BatchResult Calculate(Batch b, int threads, CancellationToken ct)
    {
        var s = b.Simulation;
        var l = Validation.Validate(s);
        if (b.Start < 0 || b.Count is < 1 or > 5000 || b.Start > s.Paths - b.Count)
            throw new ArgumentException("Некорректные границы партии.");
        var stress = s.Stress ?? new Stress("Базовый");
        int n = s.Assets.Length;
        double dt = 1.0 / s.Steps;
        double initial = s.Assets.Sum(a => a.Price * a.Quantity);
        var drift = s.Assets.Select(a => (a.Drift + stress.DriftShift
            - .5 * Math.Pow(a.Volatility * stress.VolatilityMultiplier, 2)) * dt).ToArray();
        var sigma = s.Assets.Select(a => a.Volatility * stress.VolatilityMultiplier * Math.Sqrt(dt)).ToArray();
        var losses = new double[b.Count];
        var samples = new Sample?[Math.Min(b.Count, Math.Max(0, 64 - b.Start))];
        Parallel.For(0, b.Count, new ParallelOptions
        { MaxDegreeOfParallelism = Math.Clamp(threads, 1, 16), CancellationToken = ct }, i =>
        {
            int index = b.Start + i;
            var random = new Generator(s.Seed ^ (0xD2B74407B1CE6E93UL * (ulong)(index + 1)));
            var prices = s.Assets.Select(a => a.Price * (1 + stress.Shock(a.Kind))).ToArray();
            var normals = new double[n];
            var values = index < 64 ? new double[s.Steps + 1] : null;
            if (values != null) values[0] = s.Assets.Select((a, j) => a.Quantity * prices[j]).Sum();
            for (int step = 0; step < s.Steps; step++)
            {
                if ((step & 15) == 0) ct.ThrowIfCancellationRequested();
                for (int j = 0; j < n; j++) normals[j] = random.Normal();
                double value = 0;
                for (int j = 0; j < n; j++)
                {
                    double z = 0;
                    for (int k = 0; k <= j; k++) z += l[j][k] * normals[k];
                    prices[j] *= Math.Exp(drift[j] + sigma[j] * z);
                    value += prices[j] * s.Assets[j].Quantity;
                }
                if (values != null) values[step + 1] = value;
            }
            losses[i] = initial - s.Assets.Select((a, j) => a.Quantity * prices[j]).Sum();
            if (!double.IsFinite(losses[i])) throw new ArithmeticException("Переполнение модели.");
            if (values != null) samples[i] = new Sample(index, values);
        });
        return new BatchResult(b.Start, losses, samples.Select(x => x!).ToArray());
    }

    // Эмпирический квантиль nearest-rank. Потери могут быть отрицательными (прибыль).
    public static double Quantile(double[] sorted, double confidence) =>
        sorted[Math.Clamp((int)Math.Ceiling(confidence * sorted.Length) - 1, 0, sorted.Length - 1)];

    public static Result Aggregate(Simulation s, double[] losses, Sample[] samples,
        WorkerRun[] workers, double seconds)
    {
        if (losses.Length != s.Paths || losses.Any(x => !double.IsFinite(x)))
            throw new ArgumentException("Нельзя агрегировать неполный или повреждённый результат.");
        Array.Sort(losses);
        double min = losses[0], max = losses[^1], span = max - min;
        var counts = new int[40];
        foreach (double x in losses)
            counts[span == 0 ? 0 : Math.Min(39, (int)((x - min) / span * 40))]++;
        var histogram = Enumerable.Range(0, 40).Select(i => new Bin(
            min + span * i / 40, min + span * (i + 1) / 40, counts[i])).ToArray();
        int tail = (int)Math.Ceiling(.95 * losses.Length) - 1;
        return new Result(s.Paths, s.Assets.Sum(a => a.Price * a.Quantity),
            Quantile(losses, .95), Quantile(losses, .99), losses.Skip(tail).Average(),
            losses.Average(), max, min, Quantile(losses, s.Confidence),
            losses.Count(x => x > 0) / (double)losses.Length, seconds, histogram,
            samples.OrderBy(x => x.Index).ToArray(), workers);
    }
}
