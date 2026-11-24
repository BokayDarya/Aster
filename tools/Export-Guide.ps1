[CmdletBinding()]
param([switch]$ReadOnly)
$ErrorActionPreference = 'Stop'
$taskRootPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskDocPath = Join-Path $taskRootPath 'ASTER_Подробное_руководство.docx'
$taskPdfPath = [System.IO.Path]::ChangeExtension($taskDocPath, '.pdf')
if (-not (Test-Path -LiteralPath $taskDocPath -PathType Leaf)) { throw 'Сначала создать отдельное руководство.' }
$taskWord = New-Object -ComObject Word.Application
$taskDoc = $null
try {
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskDoc = $taskWord.Documents.Open($taskDocPath, $false, [bool]$ReadOnly)
    if (-not $ReadOnly) {
        $taskDoc.AutoHyphenation = $false
        $taskDoc.Content.LanguageID = 1049
        $taskDoc.Fields.Update() | Out-Null
        foreach ($taskToc in $taskDoc.TablesOfContents) { $taskToc.Update() }
        foreach ($taskStyleId in @(-20, -21)) {
            $taskStyle = $taskDoc.Styles.Item($taskStyleId)
            $taskStyle.Font.Name = 'Times New Roman'
            $taskStyle.Font.Size = 10.5
            $taskStyle.Font.Bold = 0
            $taskStyle.Font.Color = 0
            $taskStyle.Font.AllCaps = 0
            $taskStyle.ParagraphFormat.SpaceBefore = 0
            $taskStyle.ParagraphFormat.SpaceAfter = 1
            $taskStyle.ParagraphFormat.LineSpacingRule = 0
            $taskStyle.ParagraphFormat.FirstLineIndent = 0
            $taskStyle.ParagraphFormat.LeftIndent = 0
            if ($taskStyleId -eq -21) { $taskStyle.ParagraphFormat.LeftIndent = 14.17 }
            $taskStyle.ParagraphFormat.KeepWithNext = 0
            $taskStyle.ParagraphFormat.KeepTogether = -1
        }
        $taskDoc.Repaginate()
        foreach ($taskToc in $taskDoc.TablesOfContents) { $taskToc.UpdatePageNumbers() }
        $taskDoc.Save()
    }
    $taskDoc.ExportAsFixedFormat($taskPdfPath, 17)
    Write-Output ('Exported separate guide; pages=' + $taskDoc.ComputeStatistics(2))
} finally {
    if ($null -ne $taskDoc) {
        $taskDoc.Close(0)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskDoc) | Out-Null
    }
    $taskWord.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($taskWord) | Out-Null
}
