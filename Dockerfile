FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /source
COPY src/AsterRisk/ ./
RUN dotnet publish AsterRisk.csproj -c Release -o /app --nologo
FROM mcr.microsoft.com/dotnet/runtime:8.0
WORKDIR /app
COPY --from=build /app ./
USER $APP_UID
ENTRYPOINT ["dotnet", "AsterRisk.dll"]
