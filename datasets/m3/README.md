# Dataset inicial M3

`annotations.json` contém 79 frames marcados visualmente por Codex em folhas de
contato de 480×270 pixels, com coordenadas multiplicadas por quatro para os
originais 1920×1080. Os centros e raios são aproximados, especialmente sob blur,
mão e bordas. Não foram copiados das previsões do detector. A revisão de Bruno e
Antoni ainda está pendente.

Há 50 positivos e 29 negativos. As gravações têm a mesma montagem/iluminação e
foram examinadas durante o ajuste: o conjunto é exploratório, sem holdout independente.
As duas anotações de oclusão 240/244 foram acrescentadas após a inspeção do vídeo
completo revelar saltos para distratores. Não interpretar os resultados como
garantia de precisão ou generalização.

Os originais ficam fora do Git. Neste computador estão em `C:\Users\Bruno\Downloads`.
Em outro ambiente, coloque cópias em `recordings/m3/` e confira os SHA-256 registrados.
Índices começam em zero; centros/raios estão em pixels originais, sem espelhamento.
Ausência usa `center_px: null` e `radius_px: null`. Notas indicam casos ambíguos.

Para avaliar:

```bash
python -m robosense_lab.evaluate_m3 --recordings-dir recordings/m3 --output runs/nova-avaliacao.json
```

A pontuação espacial exige centro a até `max(24 px, raio anotado / 2)`. Esse limite
é experimental, não uma tolerância física do robô. Alvo errado conta FP e FN;
erros de centro/raio e setores são calculados apenas nos acertos espaciais.
O detector não recebe os rótulos. O estado do tracker avança em todos os frames,
incluindo os não anotados. Tempos usam a mediana de três chamadas após aquecimento.
