<#
  Registra (ou remove) a tarefa agendada do Windows que roda a vigia de modelos novos toda segunda as 10:00.

  NAO e executado pelo projeto: rode voce, num PowerShell aberto pelo menu Iniciar (nao precisa de administrador).
    .\deploy\instalar-vigia-windows.ps1            # cria/atualiza a tarefa
    .\deploy\instalar-vigia-windows.ps1 -Remover   # apaga a tarefa
    .\deploy\instalar-vigia-windows.ps1 -Agora     # cria e ja dispara uma vez

  A tarefa roda `python cli.py vigia --relatorio` na pasta do projeto: varre Ollama + Hugging Face, grava
  estado\alertas.json e relatorios\AAAA-MM-DD-decisao.md. NAO baixa nem apaga nenhum modelo.
  "-StartWhenAvailable": se o computador estava desligado na segunda, roda quando ligar (maquina desligada e normal).
#>
param([switch]$Remover, [switch]$Agora)
$ErrorActionPreference = 'Stop'
$nome = 'Local Intelligence - vigia de modelos'
$pasta = Split-Path -Parent $PSScriptRoot

if ($Remover) {
    if (Get-ScheduledTask -TaskName $nome -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $nome -Confirm:$false
        Write-Host "Tarefa '$nome' removida."
    } else { Write-Host "Tarefa '$nome' nao existe." }
    return
}

$py = (Get-Command python -ErrorAction Stop).Source
$acao = New-ScheduledTaskAction -Execute $py -Argument 'cli.py vigia --relatorio' -WorkingDirectory $pasta
$gatilho = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 10:00
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
          -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $config -Force `
    -Description 'Varre Ollama e Hugging Face em busca de modelos locais novos. Nao baixa nada.' | Out-Null
Write-Host "Tarefa '$nome' criada: segundas 10:00, em $pasta"
if ($Agora) { Start-ScheduledTask -TaskName $nome; Write-Host 'Disparada uma vez.' }
