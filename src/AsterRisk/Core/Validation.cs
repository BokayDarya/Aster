namespace AsterRisk.Core;

public static class Validation
{
    public static double[][] Validate(Simulation s)
    {
        if (s.Assets is null || s.Assets.Length is < 1 or > 8)
            throw new ArgumentException("В портфеле должно быть от 1 до 8 активов.");
        if (s.Paths is < 100 or > 500000) throw new ArgumentException("Число траекторий: 100–500000.");
        if (s.Steps is not (12 or 52 or 252)) throw new ArgumentException("Число шагов: 12, 52 или 252.");
        if (s.Confidence is not (.95 or .99)) throw new ArgumentException("Уровень доверия: 0.95 или 0.99.");
        if (s.Currency is null || s.Currency.Length != 3 || !s.Currency.All(char.IsAsciiLetter))
            throw new ArgumentException("Валюта задаётся тремя латинскими буквами.");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var a in s.Assets)
        {
            if (a is null || string.IsNullOrWhiteSpace(a.Name) || a.Name.Length > 60 || !names.Add(a.Name.Trim()))
                throw new ArgumentException("Имена активов должны быть непустыми и уникальными, до 60 символов.");
            if (a.Kind is not ("stock" or "bond" or "currency"))
                throw new ArgumentException("Тип актива: stock, bond, currency.");
            Range(a.Price, .000001, 1000000, "Цена");
            Range(a.Quantity, .000001, 1000000, "Количество");
            Range(a.Drift, -1, 1, "Годовая прогнозная доходность");
            Range(a.Volatility, 0, 1, "Годовая волатильность");
        }
        if (s.Assets.Sum(a => a.Price * a.Quantity) > 1e10)
            throw new ArgumentException("Начальная стоимость портфеля не более 10 млрд.");
        var stress = s.Stress ?? new Stress("Базовый");
        if (string.IsNullOrWhiteSpace(stress.Name) || stress.Name.Length > 60)
            throw new ArgumentException("Название сценария: 1–60 символов.");
        Range(stress.DriftShift, -.5, .5, "Сдвиг доходности");
        Range(stress.VolatilityMultiplier, .1, 3, "Множитель волатильности");
        foreach (var x in new[] { stress.StockShock, stress.BondShock, stress.CurrencyShock })
            Range(x, -.9, 1, "Начальный шок");
        return Cholesky(s.Correlation, s.Assets.Length);
    }

    public static void Range(double x, double min, double max, string name)
    {
        if (!double.IsFinite(x) || x < min || x > max)
            throw new ArgumentException($"{name}: допустим диапазон {min}…{max}.");
    }

    // Положительно полуопределённые корреляции допускают нулевой диагональный элемент L.
    public static double[][] Cholesky(double[][] c, int n)
    {
        if (c is null || c.Length != n || c.Any(r => r is null || r.Length != n))
            throw new ArgumentException("Размер матрицы корреляций должен совпадать с числом активов.");
        for (int i = 0; i < n; i++)
            for (int j = 0; j < n; j++)
            {
                Range(c[i][j], -1, 1, "Корреляция");
                if (Math.Abs(c[i][j] - c[j][i]) > 1e-10)
                    throw new ArgumentException("Матрица корреляций должна быть симметричной.");
                if (i == j && Math.Abs(c[i][j] - 1) > 1e-10)
                    throw new ArgumentException("Диагональ матрицы корреляций равна 1.");
            }
        var l = Enumerable.Range(0, n).Select(_ => new double[n]).ToArray();
        for (int i = 0; i < n; i++)
            for (int j = 0; j <= i; j++)
            {
                double v = c[i][j];
                for (int k = 0; k < j; k++) v -= l[i][k] * l[j][k];
                if (i == j)
                {
                    if (v < -1e-10) throw new ArgumentException("Матрица корреляций не положительно полуопределённая.");
                    l[i][j] = Math.Sqrt(Math.Max(0, v));
                }
                else if (l[j][j] > 1e-12) l[i][j] = v / l[j][j];
                else if (Math.Abs(v) > 1e-10)
                    throw new ArgumentException("Матрица корреляций несовместима с разложением.");
            }
        return l;
    }
}
