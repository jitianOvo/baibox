# PowerShell script to switch power schemes

while ($true) {
    # 显示当前激活的电源方案
    $activeScheme = powercfg -getactivescheme
    Write-Host "当前激活的电源方案：$activeScheme"
    Write-Host ""

    # 显示菜单
    Write-Host "此修改是基于系统给的数值进行修改，并且没有恢复原电源计划的功能，如需恢复，请到电源计划中修改"
    Write-Host ""
    Write-Host "请选择一个电源方案："
    Write-Host "1. 卓越性能"
    Write-Host "2. 高性能"
    Write-Host "3. 平衡"
    Write-Host "4. 节能"

    # 获取用户输入
    $choice = Read-Host "请输入1-4"

    # 根据用户输入执行操作
    switch ($choice) {
        "1" {
            # 卓越性能：复制方案并获取新GUID
            $output = powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61
            $guid = ($output | Select-String "电源方案 GUID: (.+?) ").Matches.Groups[1].Value
            if ($guid) {
                powercfg -setactive $guid
                Write-Host "已切换到卓越性能"
            } else {
                Write-Host "无法获取卓越性能方案的GUID"
            }
        }
        "2" {
            # 高性能：复制方案并获取新GUID
            $output = powercfg -duplicatescheme 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c
            $guid = ($output | Select-String "电源方案 GUID: (.+?) ").Matches.Groups[1].Value
            if ($guid) {
                powercfg -setactive $guid
                Write-Host "已切换到高性能"
            } else {
                Write-Host "无法获取高性能方案的GUID"
            }
        }
        "3" {
            # 平衡：复制方案并获取新GUID
            $output = powercfg -duplicatescheme 381b4222-f694-41f0-9685-ff5bb260df2e
            $guid = ($output | Select-String "电源方案 GUID: (.+?) ").Matches.Groups[1].Value
            if ($guid) {
                powercfg -setactive $guid
                Write-Host "已切换到平衡"
            } else {
                Write-Host "无法获取平衡方案的GUID"
            }
        }
        "4" {
            # 节能：复制方案并获取新GUID
            $output = powercfg -duplicatescheme a1841308-3541-4fab-bc81-f71556f20b4a
            $guid = ($output | Select-String "电源方案 GUID: (.+?) ").Matches.Groups[1].Value
            if ($guid) {
                powercfg -setactive $guid
                Write-Host "已切换到节能"
            } else {
                Write-Host "无法获取节能方案的GUID"
            }
        }
        default {
            Write-Host "无效的输入，请输入1-4"
        }
    }

    # 显示当前激活的电源方案
    $activeScheme = powercfg -getactivescheme
    Write-Host "当前激活的电源方案：$activeScheme"
    Write-Host ""
}