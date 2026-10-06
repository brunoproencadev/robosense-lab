# Validação M3 — 05/10/2026

## Plano e entrega

Inspecionar gravações antes dos ajustes; reutilizar contratos e perfil M1; dividir
a imagem em Left/Front/Right; ajustar um perfil óptico; acompanhar medidas com um
círculo; avaliar amostras anotadas; comparar resoluções; testar reprodução e
preservar firmware/testes. Esse plano foi apresentado antes das mudanças.

Foram entregues fonte de vídeo, detector M3, associação temporal, CLI com prévia
Tk, exportação de vídeo e logs, dataset inicial, avaliador, demonstração H.264 e
AGENTS.md para continuidade. M1/M2 e o comando de setores F/D/E/A continuam disponíveis.

## Gravações e ambiente

| Arquivo | Frames | FPS médio | Duração aproximada |
| --- | ---: | ---: | ---: |
| WIN_20261005_14_19_38_Pro.mp4 | 522 | 21,082 | 24,76 s |
| WIN_20261005_14_20_11_Pro.mp4 | 488 | 21,085 | 23,14 s |
| WIN_20261005_14_21_40_Pro.mp4 | 525 | 21,081 | 24,90 s |

Resolução original 1920×1080; Windows/Python 3.14.5, NumPy 2.5.3, OpenCV 4.14.0,
PySerial 3.5. Os SHA-256 dos originais estão no dataset e nos resumos.
Nenhuma dependência de execução foi adicionada. Tk é opcional; imageio-ffmpeg
0.6.0 foi usado somente para converter os vídeos publicados em H.264.

## Uso

```powershell
.\.venv\Scripts\python.exe -m robosense_lab.m3 "C:\Users\Bruno\Downloads\WIN_20261005_14_20_11_Pro.mp4" --output-dir runs/m3-novo --preview
.\.venv\Scripts\python.exe -m robosense_lab.evaluate_m3 --recordings-dir "C:\Users\Bruno\Downloads" --output runs/m3-avaliacao-nova.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Pode passar três arquivos à CLI M3. A pasta de saída deve ser nova; a avaliação
também recusa sobrescrever um relatório. Sem `--preview`, funciona sem desktop/Tk.
No Linux substitua o Python pelo `.venv/bin/python`. Na Pi com desktop, Tk pode
exigir o pacote `python3-tk`. Ainda não executamos o M3 fisicamente na Pi.

A janela reproduz as imagens conforme timestamps do decoder; Esc fecha e deixa
log parcial com `run_error`, sem `run_summary`. Não processa uma webcam.
A CLI exporta MP4/mp4v em até 960 pixels de largura, JPEG, JSONL e resumo.
Vídeos exportados são silenciosos e CFR pelo FPS médio; os logs preservam os
timestamps de mídia originais. Há pequenas diferenças possíveis de cadência VFR.

Os [três vídeos publicados](../artifacts/m3/index.html) usam H.264 para reprodução
em navegador. Abra o HTML local após clonar o repositório; links HTML no GitHub
mostram o código, não hospedam a demonstração. A conversão é reproduzível:

```powershell
.\.venv\Scripts\python.exe -m pip install imageio-ffmpeg
.\.venv\Scripts\python.exe tools/package_m3.py --run-dir runs/SUA_EXECUCAO --evaluation runs/SUA_AVALIACAO.json --output-dir artifacts/SUA_DEMO_NOVA
```

## Perfil e setores

Processa largura 320 por padrão, com interpolação AREA para reduzir custo e ruído.
Converte resultados para pixels originais. Ignora 15% superiores da imagem,
configuráveis via `--roi-top`; isso precisa ser revisto se a câmera mudar.

HSV OpenCV: H 0–35 ou 170–179, S ≥ 40, V ≥ 80. Fechamento 3×3 e abertura 5×5,
com borda preta na abertura para eliminar ligações no limite da ROI. Forma é
avaliada no casco convexo: circularidade ≥ 0,5, ocupação do círculo ≥ 0,4,
raio de 2% a 9% da largura processada e área ≤ 8% da imagem. Seleciona o maior
candidato válido. Bola menor que esses limites ou fora da ROI pode ser perdida.

Associação usa a última medida durante até 2 segundos de mídia: raio atual entre
0,55 e 1,8 vezes o anterior e deslocamento ≤ `max(4 raios, 15% da largura)`.
Essa referência filtra candidatos, sem desenhar posição antiga ou prever bola
oculta. Círculos cortados nas bordas horizontais não atualizam o raio de referência.
Mudança de câmera, domínio ou regressão de timestamp elimina a referência.
Movimento brusco ou mudança forte de distância pode exigir reacquisição após a
expiração: esses limites são de bancada, ainda não calibrados para o robô.

Left: x < largura/3; Front: largura/3 ≤ x < 2×largura/3; Right: restante.
A classificação usa o centro, sem espelhamento e sem histérese. Uma bola sobre a
fronteira pode alternar setor com pequenas variações. Não é ângulo do robô nem
substitui a montagem das câmeras F/D/E/A ou o protocolo serial existente.

## Avaliação inicial

[Dataset](../datasets/m3/README.md): 79 anotações visuais aproximadas, 50 positivos,
29 negativos, sujeitas à revisão da equipe. O perfil foi ajustado examinando essas
gravações; não há holdout independente. Não extrapolar os percentuais para outro campo.

Um centro a até `max(24 px, meio raio anotado)` conta como acerto espacial.
Alvo errado conta FP e FN. Localização/raio e setor são avaliados só nos acertos.
O tracker percorre todos os frames em ordem, sem receber rótulos.

| Perfil | TP / FN / FP / TN | Precisão | Recall | Erro médio centro | Mediana detecção + associação | P95 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| M1 original | 0 / 50 / 0 / 29 | Indefinida | 0% | Indefinido | 4,72 ms | 5,86 ms |
| M3 320 (padrão) | 48 / 2 / 0 / 29 | 100% | 96% | 6,53 px | 2,12 ms | 3,14 ms |
| M3 640 | 46 / 4 / 0 / 29 | 100% | 92% | 5,41 px | 2,57 ms | 3,50 ms |
| M3 960 | 46 / 4 / 0 / 29 | 100% | 92% | 6,41 px | 2,42 ms | 3,21 ms |
| M3 1920 | 32 / 18 / 1 / 29 | 96,97% | 64% | 4,36 px | 9,96 ms | 11,65 ms |

Em 320: erro de centro P95 11,04 px, erro médio do raio 5,44 px, setor correto em
48/48 acertos espaciais. Duas perdas são os frames 240 e 244 sob a mão no vídeo
próximo. O erro de centro não inclui essas perdas. Os rótulos aproximados não
permitem afirmar precisão física de 6,53 pixels. São referência inicial de imagem.

Tempos: mediana de três chamadas por amostra após aquecimento, incluindo resize,
HSV, formas e associação, sem aquisição/exportação. Redução de resolução também
suaviza a máscara; por isso a versão maior não necessariamente detecta melhor.
O relatório com amostras e valores brutos está em
[evaluation.json](../artifacts/m3/evaluation.json).

## Execução completa e reprodução

Os 1535 frames foram decodificados, processados e exportados. Os vídeos H.264 têm
522, 488 e 525 frames, verificados na conversão. Contagens de setores completas
estão nos JSONL/resumos; não são ground truth dos frames não anotados.

| Vídeo | Média detector/associação | P95 detector/associação | P95 decode/detecção/render/log/MP4 | Tempo de exportação |
| --- | ---: | ---: | ---: | ---: |
| Próximo | 2,48 ms | 3,27 ms | 12,32 ms | 5,17 s |
| Movimento | 2,62 ms | 3,34 ms | 12,38 ms | 5,15 s |
| Distante | 2,81 ms | 3,65 ms | 14,60 ms | 5,96 s |

Esse tempo por etapa exclui espera e apresentação Tk e a conversão posterior
H.264. Não é latência óptica/câmera/tela. A gravação fornece aproximadamente
47,4 ms entre frames, e a máquina local foi suficiente para o replay testado.

A janela Tk foi executada no vídeo de movimento completo: **488 frames em
23,13 s**, acompanhando a gravação de 23,14 s. O registro local está em
`runs/m3-preview-check/`; cópia do resumo em `artifacts/m3/replay-summary.json`.
**62 testes passaram**, cobrindo leitura, EOF/falha, fechamento, coordenadas,
reflexos, ausência, setores, bordas, referência temporal, pontuação e proteção
de saídas. Nesta sandbox Windows, TEMP/TMP foram apontados para `runs/test-temp`
para contornar a permissão do diretório temporário isolado; o código não depende disso.

O SHA-256 do firmware permanece
`70fae2b690a0a7be5cc43dd1b7fb4a5fbfa22c7e4ac2ad20e71c7747c43b2513`.

## Pendências

Revisão humana das anotações, nova gravação independente com diferentes luzes,
bola menor/mais distante, objetos laranja sem bola, oclusões longas e movimento
da própria câmera. HSV e associação ainda podem confundir objetos parecidos.
Não há métricas completas de acerto para todos os 1535 frames.

M4: uma webcam na Pi4B, com aquisição e medição de FPS/atraso real, temperatura,
perda/reconexão e consumo. Depois ampliar câmeras. Sem integração de motores ou
receptor GIGA neste M3; a bola filmada é laranja visível, não prova de percepção
de uma bola infravermelha específica da competição.
