# RoboSense Lab

Infraestrutura experimental de percepção para RoboCup Junior Soccer, Infrared League.
O M1 funciona sem webcams, Raspberry Pi ou Arduino: gera imagens, detecta um alvo
sintético e registra observações e métricas. Não envia comandos ao robô.

## Preparação

Requer Python 3.12 ou superior e acesso ao PyPI na instalação inicial. Execute os
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

## Limites deste milestone

O detector usa limiar de cor HSV, área mínima e circularidade, selecionando o
maior candidato válido. A confiança não é uma probabilidade calibrada. Um objeto
laranja parecido pode causar falso positivo. Esses limiares são um baseline para
imagens sintéticas e não foram validados para a bola infravermelha real.

O M1 não simula física, óptica, ruído, oclusão, comunicação ou motores. Não há
tracking, fusão, aquisição USB ou integração com o GIGA. O protocolo `Camera`
define o ponto onde uma fonte real poderá ser adicionada sem alterar o detector.

Consulte [a arquitetura](docs/architecture.md), [os milestones](docs/milestones.md)
e [a validação registrada](docs/validation-m1.md). O sketch fornecido pelo usuário
está em [firmware/giga_baseline](firmware/giga_baseline/README.md).
