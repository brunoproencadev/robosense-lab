# RoboSense Lab

Infraestrutura experimental de percepção para RoboCup Junior Soccer, Infrared League.
Os milestones M1 e M2 funcionam sem webcams, Raspberry Pi ou Arduino: geram imagens,
detectam um alvo sintético e registram observações e métricas. O M2 compara ruído,
oclusão, perda da fonte e idade dos frames. Não envia comandos ao robô.

## Preparação

Requer Python 3.11 ou superior e acesso ao PyPI na instalação inicial. Execute os
comandos na raiz do projeto. O ambiente virtual mantém as dependências isoladas.

Windows / PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m robosense_lab --frames 60 --output runs/m1.jsonl
```

Linux / Raspberry Pi (ainda sem validação neste ambiente):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m robosense_lab --frames 60 --output runs/m1.jsonl
```

No Linux, a distribuição pode exigir o pacote `python3-venv`. A disponibilidade
das versões de Python e dos pacotes OpenCV depende do sistema e da arquitetura da
Raspberry Pi; isso será verificado na etapa de hardware.

Não é necessário ativar o ambiente virtual. O comando usa diretamente seu Python.
Se o arquivo de saída já existir, escolha outro nome: o programa não sobrescreve
experimentos. `--frames` aceita somente inteiros positivos. Códigos de saída:
`0` indica conclusão normal; `1`, erro de execução tratado; `2`, argumentos inválidos.

## O que você verá

O terminal mostra o resumo e o caminho do registro. Não há janela gráfica.
O arquivo contém um evento `run_start`, uma `observation` por frame e um
`run_summary` ao término normal. Cada linha é um objeto JSON independente,
com `schema_version: 1`. O log é descarregado após cada evento; isso não garante
persistência diante de perda de energia. Uma execução interrompida pode deixar
um arquivo parcial; a ausência de `run_summary` indica que não houve conclusão.

Observações incluem:

| Campo | Significado |
| --- | --- |
| `camera_id`, `sequence` | Origem e índice do frame, começando em zero |
| `timestamp_ns`, `clock_domain` | Instante de captura e domínio do relógio |
| `received_timestamp_ns`, `frame_age_ns` | Entrega e idade do frame no mesmo relógio da captura |
| `ball_detected` | Se o detector encontrou um candidato |
| `ball_x`, `ball_y` | Centro em pixels; `null` se não detectado |
| `confidence` | Circularidade de 0 a 1; zero sem detecção |
| `processing_ns` | Tempo medido apenas na chamada do detector |
| `expected_center_px` | Resposta conhecida da simulação, usada só na avaliação |
| `localization_error_px` | Distância entre centro detectado e esperado; `null` quando não comparável |

As imagens têm 320 × 240 pixels, em BGR. O canto superior esquerdo é `(0, 0)`;
`x` cresce para a direita e `y` para baixo. Cada quinto frame não contém bola.
Os demais contêm um círculo laranja de raio 12 em fundo verde.

O relógio `simulation` avança virtualmente a 30 Hz, sem aguardar tempo real.
**Isso não significa que o programa ou o hardware alcance 30 FPS.**
Imagens, timestamps virtuais e posições são reproduzíveis; tempos de processamento
variam conforme a máquina e a execução. `mean_processing_ms` não inclui aquisição,
gravação ou comunicação, portanto não é latência ponta a ponta.

Precisão = TP / (TP + FP); recall = TP / (TP + FN). TP/FP/FN/TN avaliam presença
por frame. O erro de localização é calculado separadamente, somente quando há
bola esperada e detectada. Denominadores vazios produzem `null`, não resultados
inventados. Uma falha de câmera gera `camera_error` e aborta a execução; não conta
como frame sem bola.

Para gerar um painel PNG da mesma execução sintética, use:

```powershell
.\.venv\Scripts\python.exe -m robosense_lab.demo --output artifacts/demo-m1.png
```

O painel mostra exemplos positivo e negativo, o centro calculado e métricas da
execução. Imagem e registro usam o mesmo cenário e o detector M1. O programa cria
um PNG novo e recusa sobrescrever arquivos. A amostra entregue está em
[artifacts/demo-m1.png](artifacts/demo-m1.png).

## M2: cenários adversos

Execute a comparação de sete cenários em uma pasta nova:

```powershell
.\.venv\Scripts\python.exe -m robosense_lab.experiments --frames 60 --seed 42 --output-dir runs/meu-m2
```

No Linux, use `.venv/bin/python` no lugar do executável Windows.
O comando produz um JSONL por cenário e `summary.json`, com parâmetros, versões,
resultados e status. A pasta de saída precisa ser nova. Perda de câmera planejada
é registrada como `camera_error` com métricas parciais; o comparador continua os
outros cenários. Uma falha inesperada aborta a comparação.

| Cenário | Condição |
| --- | --- |
| `baseline` | M1, sem perturbações |
| `noise` | Ruído gaussiano BGR, desvio padrão 45, semente informada |
| `partial_occlusion` | Cobertura de metade da largura da bola, arredondada para pixels |
| `full_occlusion` | Cobertura completa da bola |
| `camera_loss` | Falha terminal no índice `frames // 2` |
| `delay_50ms` | Entrega virtual após 50 ms, aceita |
| `delay_200ms` | Entrega virtual após 200 ms, rejeitada |

O limite experimental é **100 ms**, inclusive. A idade é avaliada antes do
detector, na entrega do frame. O atraso é virtual; não adiciona `sleep`, fila real
ou latência física. Esse limite não foi validado para decisões no robô.

Para executar uma condição isolada ou combinar perturbações:

```powershell
.\.venv\Scripts\python.exe -m robosense_lab --noise-std 45 --seed 42 --occlusion 0.5 --output runs/ruido-oclusao.jsonl
.\.venv\Scripts\python.exe -m robosense_lab --delay-ms 200 --max-frame-age-ms 100 --output runs/atrasados.jsonl
.\.venv\Scripts\python.exe -m robosense_lab --loss-at-frame 30 --output runs/perda-camera.jsonl
```

`--loss-at-frame` usa índice começando em zero; deve ser menor que `--frames`.
Na execução isolada, falha de câmera gera saída `1`, um registro parcial e nenhum
`run_summary`. O fim normal continua sendo diferente de falha.

O resumo distingue `frames_received` (recebidos), `frames` (processados) e
`stale_frames` (rejeitados por idade). TP/FP/FN/TN, precisão, recall e erro de centro
consideram **somente frames processados**. Frames rejeitados não são falsos
negativos; precisam ser avaliados junto com a quantidade de dados disponíveis.
Se todos forem rejeitados, precisão, recall, erro e tempo de processamento são
`null`. O evento `frame_rejected` registra o motivo e a idade, sem apresentar uma
observação de bola.

O ground truth mantém a posição física da bola mesmo quando ela está coberta.
Assim, bola totalmente oculta e não detectada conta como falso negativo de
percepção; isso é uma limitação esperada de uma única imagem. Ruído e oclusão são
aplicados aos pixels antes da detecção; o detector continua sem acesso à resposta.
Mesma semente e mesmas versões reproduzem as imagens; tempos medidos variam.

Veja [a validação M2](docs/validation-m2.md) e
[o resumo observado](artifacts/m2-summary.json).

## Limites deste milestone

O detector usa limiar de cor HSV, área mínima e circularidade, selecionando o
maior candidato válido. A confiança não é uma probabilidade calibrada. Um objeto
laranja parecido pode causar falso positivo. Esses limiares são um baseline para
imagens sintéticas e não foram validados para a bola infravermelha real.

O M2 simula perturbações de pixels e atraso de entrega. Ainda não simula física,
óptica ou motores. Não há tracking, fusão, aquisição USB ou integração
com o GIGA. Não há recuperação automática após perda da fonte. O protocolo
`Camera` define o ponto onde uma fonte real poderá ser adicionada sem alterar o
detector.

## Setores F/D/E/A e PySerial

```powershell
.\.venv\Scripts\python.exe -m robosense_lab.sectors --frames 6 --serial-port loop:// --output runs/setores.jsonl
```

Quatro fontes simuladas produzem `F`, `D`, `E`, `A`, `SEM_BOLA` e `F D`.
Sobreposição preserva todos os setores detectados. `SEM_DADOS` identifica dados
inválidos, sem reutilizar direção antiga. Omita `--serial-port` para usar somente
o terminal. O loopback do PySerial confere os bytes enviados sem precisar de placa.
Na serial, o formato é JSON por linha, com setores, estado, sequência e timestamp.

Veja [a lógica e o protocolo de bancada](docs/sectors-and-serial.md) e
[a preparação para Raspberry Pi 4B](docs/raspberry-pi4b.md). O alvo é Raspberry Pi
OS de 64 bits/Python >= 3.11; execução real na placa ainda não foi validada.

Consulte [a arquitetura](docs/architecture.md), [os milestones](docs/milestones.md)
e [a validação registrada](docs/validation-m1.md). O sketch fornecido pelo usuário
está em [firmware/giga_baseline](firmware/giga_baseline/README.md).
