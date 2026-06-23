# Windows 定时任务设置脚本
# 以管理员身份运行此脚本

$taskName = "InvestmentTrackerDaily"
$scriptPath = "E:\AI_investment_observation\update.bat"
$description = "每日投资数据更新 - 北京时间下午16:00和晚上20:00"

# 删除已有同名任务
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建触发器：每天16:00和20:00
$trigger1 = New-ScheduledTaskTrigger -Daily -At "16:00"
$trigger2 = New-ScheduledTaskTrigger -Daily -At "20:00"

# 创建动作
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$scriptPath`""

# 设置选项（不要求用户登录、允许按需运行）
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

# 注册任务
Register-ScheduledTask -TaskName $taskName `
    -Description $description `
    -Trigger $trigger1, $trigger2 `
    -Action $action `
    -Settings $settings `
    -RunLevel Limited `
    -Force

Write-Host "✅ 定时任务已创建！" -ForegroundColor Green
Write-Host "   任务名: $taskName"
Write-Host "   运行时间: 每天 16:00 和 20:00"
Write-Host ""
Write-Host "💡 手动运行测试: schtasks /run /tn $taskName"
