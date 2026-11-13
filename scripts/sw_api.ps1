# Offline SolidWorks API lookup, by reflection over the installed .NET interop assemblies.
#   sw_api.ps1 FeatureFillet*            members (methods/properties) whose name matches, on any interface
#   sw_api.ps1 IFeatureManager.*Chamfer* restrict to one interface
#   sw_api.ps1 -Enum *FilletOptions*     enums whose name matches, with integer values
#   sw_api.ps1 -Enum * -Value Fillet     enum members whose name matches across all enums
param([string]$Pattern = "*", [switch]$Enum, [string]$Value = "")

$clsid = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\SldWorks.Application\CLSID").'(default)'
$exe = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\CLSID\$clsid\LocalServer32").'(default)'
$dir = Split-Path ($exe.Trim('"'))

if ($Enum) {
    $asm = [Reflection.Assembly]::LoadFrom("$dir\SolidWorks.Interop.swconst.dll")
    foreach ($t in ($asm.GetTypes() | Where-Object { $_.IsEnum -and $_.Name -like $Pattern } | Sort-Object Name)) {
        $names = [Enum]::GetNames($t) | Where-Object { $Value -eq "" -or $_ -like "*$Value*" }
        if (-not $names) { continue }
        "$($t.Name)"
        foreach ($n in $names) { "    $n = $([Convert]::ToInt64([Enum]::Parse($t, $n)))" }
    }
    return
}

$asm = [Reflection.Assembly]::LoadFrom("$dir\SolidWorks.Interop.sldworks.dll")
$iface, $member = "*", $Pattern
if ($Pattern -like "*.*") { $iface, $member = $Pattern.Split(".", 2) }
foreach ($t in ($asm.GetTypes() | Where-Object { $_.IsInterface -and $_.Name -like $iface -and $_.Name -like "I*" } | Sort-Object Name)) {
    foreach ($m in ($t.GetMembers() | Where-Object { $_.Name -like $member } | Sort-Object Name)) {
        if ($m.MemberType -eq "Method") {
            if ($m.Name -like "get_*" -or $m.Name -like "set_*") { continue }
            $ps = ($m.GetParameters() | ForEach-Object { "$($_.ParameterType.Name) $($_.Name)" }) -join ", "
            "$($t.Name).$($m.Name)($ps) -> $($m.ReturnType.Name)"
        } elseif ($m.MemberType -eq "Property") {
            $rw = if ($m.CanWrite) { "get/set" } else { "get" }
            "$($t.Name).$($m.Name) : $($m.PropertyType.Name)  [$rw]"
        }
    }
}
