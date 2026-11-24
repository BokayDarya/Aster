using System.Text.Json;
using System.Text.Json.Serialization;

namespace AsterRisk.Core;

public static class Json
{
    public static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web)
    {
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 32
    };
    public static JsonElement Element<T>(T value) => JsonSerializer.SerializeToElement(value, Options);
    public static T Parse<T>(JsonElement value) => value.Deserialize<T>(Options)
        ?? throw new ArgumentException("Пустые данные.");
}

public sealed record Asset(string Name, string Kind, double Price, double Quantity,
    double Drift, double Volatility);
public sealed record Stress(string Name, double DriftShift = 0, double VolatilityMultiplier = 1,
    double StockShock = 0, double BondShock = 0, double CurrencyShock = 0)
{
    public double Shock(string kind) => kind switch
    { "stock" => StockShock, "bond" => BondShock, "currency" => CurrencyShock, _ => 0 };
}
public sealed record Simulation(Asset[] Assets, double[][] Correlation, int Paths = 100000,
    int Steps = 12, ulong Seed = 2026, double Confidence = .95, Stress? Stress = null,
    string Currency = "BYN");
public sealed record Batch(Simulation Simulation, int Start, int Count);
public sealed record Sample(int Index, double[] Values);
public sealed record BatchResult(int Start, double[] Losses, Sample[] Samples);
public sealed record Bin(double From, double To, int Count);
public sealed record WorkerRun(string Endpoint, int Batches, int Paths, int Failures);
public sealed record Result(int Paths, double InitialValue, double Var95, double Var99,
    double ExpectedShortfall95, double MeanLoss, double WorstLoss, double BestLoss,
    double SelectedVar, double LossProbability, double ElapsedSeconds,
    Bin[] Histogram, Sample[] Samples, WorkerRun[] Workers);
public sealed record Submit(Simulation Simulation, string RequestId);
public sealed record JobView(string Id, string RequestId, string Status, int Completed,
    int Total, string? Error, Result? Result, Simulation Simulation, DateTimeOffset Created);
