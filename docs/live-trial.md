# Ensaio ao vivo — 06/10/2026

Preparação para M4: câmera local/virtual via OpenCV, perfil M3 e associação,
Left/Front/Right e círculo atual pela janela Tk. Não altera firmware nem serial.
Plano apresentado antes da implementação: escolher câmera, reutilizar detector
e desenho, registrar falhas e fechar a fonte ao sair.

CLI: `python -m robosense_lab.live --device 2 --output-dir runs/NOME_NOVO`.
Para outra máquina, confirme o índice. Esc termina normalmente; falha de captura
registra `run_error` sem resumo de sucesso. Pasta existente é recusada.
`--frames N --no-preview` faz teste limitado. Sem `--frames`, a janela continua
até Esc. O recorte padrão é zero para o ensaio doméstico; não recalibramos HSV.

Windows usa DirectShow; outras plataformas usam o backend padrão OpenCV.
Solicita 640×480 e buffer de um frame, sem presumir que o driver aceite.
Log registra dimensões realmente entregues. Timestamp `host_delivery_monotonic`
é gerado ao terminar read(): não é captura óptica nem permite medir o atraso
do celular/Wi-Fi/USB/driver. FPS do resumo inclui abertura e interface, não FPS
do sensor. O tracker só usa observações atuais; não desenha posição perdida.

65 testes locais passaram (62 anteriores + 3 de captura ao vivo), verificando
metadados, falha, fechamento, CLI finita e proteção de registros existentes.
Ensaio de índice 2: 60 frames 640×480 em 2,97 s, cerca de 20,20 frames processados/s.
Essa fonte foi inspecionada e entregava **imagem azul uniforme**: demonstra
funcionamento da captura/interface, não detecção da bola nem conexão ativa do celular.
Índices 0 e 1 não abriram nos backends DirectShow/MSMF neste ensaio. Índice 3 é
outra fonte virtual e não foi usado para capturar imagens.

Pendente: localizar o cliente ativo do usuário, confirmar imagem real e testar
bola/réplica, fundos e oclusões. Nenhuma métrica de acerto ao vivo está disponível.
Diagnóstico posterior: cliente ativo em `C:\Program Files\DroidCam\Client\bin\64bit`
usa a saída `DroidCam Video` (índice 1), diferente da fonte antiga azul.
DirectShow e MSMF não abriram essa saída mesmo fora do isolamento; FFmpeg por
nome retornou `Could not RenderStream to connect pins` / `I/O error`.
O log do cliente registra início da câmera virtual. Pedido de fechamento normal
não encerrou o processo (possível permanência na bandeja); reinício não confirmado.
Próximo passo: sair pelo menu do cliente e reabrir, então repetir captura direta.
Após reinício confirmado pelo usuário, a saída virtual voltou a iniciar no log,
mas DirectShow continuou falhando. FFmpeg enumerou formatos YUY2 e também falhou
com 640×480/30 FPS explícitos. Reinício do cliente não resolveu; aquisição real
continua bloqueada no driver, antes do detector. Próximo passo: reiniciar Windows
e repetir; se persistir, reparar o driver oficial DroidCam.
Alternativa posteriormente autorizada: OBS Virtual Camera, índice 3, abriu com
frames 640×480 não uniformes (desvio padrão global 38,88 em um frame). CLI com
janela visível iniciada para ensaio manual. Isso não comprova que a imagem seja
a do celular nem a qualidade da detecção; confirmação do usuário pendente.

## Ajuste após falha doméstica

Captura enviada pelo usuário mostrou bola junto à mão e falso alvo no canto.
No recorte da imagem (634×443, sem rodapé), o perfil anterior selecionou pele
em (188,81; 319,40). A máscara unia mão/bola, e os limites M3 supunham bola
pequena. Perfil `live-orange-v1`: saturação mínima 160, valor mínimo 45,
raios relativos de 0,8% a 22% da largura, abertura 3×3 e filtro de solidez.
Resultado no mesmo recorte: centro (293,78; 298,74), raio 61,55 px, na região
da bola. Sem rótulo independente: não é métrica de precisão ou generalização.
Screenshot pessoal não foi copiado para o Git.

Referência ao vivo expira após 0,3 s sem nova medida aceita (M3 mantém 2 s).
Medidas que cruzam qualquer borda não alimentam a referência de tamanho.
67 testes passaram, incluindo bola grande/pequena encostada em pele sintética,
ausência e recuperação após salto. Firmware preservado pelo SHA-256 esperado.
CLI modificada aberta novamente em OBS/640×480, com pasta nova em runs/.
Pendente avaliação manual de luz, movimento, bola menos saturada e distratores.
Ainda pode detectar outros objetos laranja; não é solução universal.

## Segunda falha e perfil v2

Novo screenshot confirmou falso alvo na mão. Aumentar saturação não separou a
bola em todas as luzes: o contorno combinado foi rejeitado por solidez, restando
pequenos fragmentos de pele. `live-orange-v2` acrescenta círculos Hough no canal
de saturação e valida candidatos por cobertura de cor no núcleo (85%) e contraste
com anel externo (35%). Contornos e círculos passam pelas mesmas validações de
tamanho, cor e associação; não há reconhecimento semântico ou modelo treinado.

Nos recortes 640×443 dos screenshots pessoais: centros (286,29; 303,57), raio
53,70 px, e (354,72; 312,02), raio 36,68 px. Ambos estão na região da bola por
inspeção visual, sem rótulos independentes. Medianas de 20 execuções por imagem:
14,36 e 14,62 ms neste Windows, incluindo redimensionamento; não são latência
ponta a ponta nem prova de desempenho na Pi. Screenshots ficam fora do Git.
68 testes passaram, com regressão de bola encostada em região de cor conectada.
CLI v2 aberta em OBS, com pasta nova `runs/obs-live-v2-*`. Validar ausência real,
distratores, movimento, oclusão e outras iluminações antes de declarar robustez.

## Movimento rápido e perfil v3

Usuário relatou perdas e mão como alvo. Associação rígida vetava deslocamentos
maiores que 15% da largura ou quatro raios até expirar a referência. No perfil
ao vivo a continuidade agora aumenta moderadamente a pontuação, sem vetar novos
candidatos válidos. M3 conserva o veto original. Nenhuma coordenada é prevista
ou repetida quando não existe medida atual.

`live-orange-v3` exige também núcleo laranja (H 5–30, S >=160, V >=80 em 30%
do núcleo), permite cobertura total de 60% e acrescenta círculos pequenos pela
intensidade. Avaliação do núcleo/anel usa somente o recorte local do candidato.
69 testes passaram: salto de 400 px em 0,1 s é aceito, ausência continua sem
coordenadas e região vermelha circular sem laranja é rejeitada (sintéticos).

Três screenshots: centros (286,29;303,57), (354,72;312,02), (351,45;296,33).
Raios 53,70/36,68/38,22 px. O terceiro recorte exclui 5 linhas superiores e
rodapé; ainda há superestimação do raio incluindo mão. Isso é pendência real,
não correção completa de precisão. Medianas de 20 execuções: 16,78/18,62/17,60 ms
no Windows, sem equivalência a atraso óptico ou desempenho Pi.
Janela OBS v3 iniciada em pasta nova. Para medir perdas, borrão e falsos alvos
é necessária sequência real anotada (rápido/lento/sem bola), não screenshots.

## Limites confirmados com mão ao fundo e aproximação

Dois screenshots adicionais confirmaram limites do v3. No primeiro recorte
634×438, centro (300,88;303,37), raio 34,03 px inclui pele. No segundo recorte
643×443, não há detecção mesmo sem referência temporal: a falha também ocorre
no detector independente, não é somente associação ou idade de dados.
Máscara de cor após morfologia une regiões; componente maior tem solidez 0,66,
cobertura 0,55 e apenas 0,04 de núcleo laranja na análise a 320×220. Rejeitado
pelos filtros. Bola próxima apresenta borrão, oclusão e corte à esquerda;
não é evidência de que somente aumentar o raio máximo resolva.
Nenhum limiar novo aplicado nesta investigação. Próxima evidência necessária:
sequência com bola sozinha, mão sem bola, mão atrás, aproximação e movimento,
para comparar perdas/falsos alvos e calibrar sem ajuste isolado a screenshots.

## Vídeo doméstico e perfil v4 — 06/10/2026

Fonte fornecida: `2026-10-06 19-24-12.mp4`, 1920×1080, 3077 frames,
60 FPS **da gravação da tela**, 51,28 s. SHA-256:
`70bdd28b0d1523abd2d538dd1985e78d08142e9c97225a074c8c455bd1bb655a`.
Original permanece fora do Git no caminho fornecido pelo usuário. Crop da
janela da câmera: x=36, y=60, largura=640, altura=444; frames [90,2960).
O vídeo contém círculos/textos do detector anterior: avaliação não equivale a
pixels crus da câmera. Duplicação da tela e Wi-Fi não permitem medir FPS do sensor.

Plano executado: inspecionar sequência, separar rótulos aproximados do detector,
comparar pixels iguais e testar pipeline completo. `datasets/live/home-20261006.json`
contém 18 amostras (16 presentes, 2 ausentes), com caixas visíveis aproximadas.
Raios anotados são metade da maior dimensão; réplica aparenta formato oval.
Trecho borrado tem caixa especialmente incerta. Ajuste usa estas amostras;
não há teste independente, nem validação de todos os frames ou falsos positivos
em todos os contextos. Revisão humana dos rótulos pendente.

Diagnóstico: exigir S>=160 perdia reflexos amarelos; exigir 30% de núcleo laranja
perdia sombra vermelha. Círculos Hough favoreciam fragmentos e incluíam pele.
v4 usa contornos com cor/brilho combinados: S+V>=370, amarelo com S+V>=330,
ou S>=210/V>=80; mantém hue vermelho/amarelo e mínimo de brilho/saturação.
Solidez/forma filtram candidatos; 2% de suporte laranja evita vermelho puro.
Raio máximo passa a 40% da largura para aproximação. Removidas as duas buscas
Hough. Continuidade segue preferência, sem previsão nem veto de salto no vivo.
Limiares M1/M3 preservados. Nenhuma dependência de execução nova.

Comparação em **iguais recortes JPEG95** das 18 amostras, detector independente:

| Perfil | TP | FP | FN | TN | Erro médio centro | Erro médio raio | Mediana detector |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| v3 | 8 | 2 | 8 | 2 | 18,43 px | 10,95 px | 25,16 ms |
| v4 | 14 | 0 | 2 | 2 | 9,78 px | 4,91 px | 1,22 ms |

Métrica usa `evaluate_m3.score`: alvo com erro maior que max(24 px, raio/2)
conta FP+FN. Essa tolerância e as caixas aproximadas limitam a conclusão.
Zero FP se refere somente a essas amostras; há apenas dois negativos.

Pipeline completo decodificou 3077 frames e processou 2870 crops diretamente
do MP4, usando tracker e timestamps da mídia. Detector: mediana 1,59 ms,
p95 2,91 ms no Windows. 2077 frames tiveram medida; isso não é taxa de acerto.
Nas 18 amostras: 14 TP, 0 FP, 2 FN, 2 TN; erro centro 12,28 px, erro raio
7,74 px. Os dois FN são bolas pequenas/escuras; borrão, oclusão, cor de pele
semelhante e corte extremo ainda podem perder/deslocar medida. Nada prova
estabilidade ao vivo, latência ponta a ponta ou desempenho na Raspberry Pi.

Reprodução (pasta de saída nova):

```powershell
.\.venv\Scripts\python.exe scripts\validate_live_video.py "D:\aNova pasta\Desktop\coisas after\2026-10-06 19-24-12.mp4" --output-dir runs/home-v4-NOVO
```

JSON comparativo sem imagens pessoais: `artifacts/live/home-20261006-report.json`.
Execução local: `runs/home-video-v4-full/`; vídeo `v4-demo-h264.mp4`, círculos
**azuis são v4, verdes pertencem à gravação original**. Exportação H.264 usa
imageio-ffmpeg já instalado, opcional; CLI reproduz MP4/mp4v sem essa dependência.
70 testes passaram, incluindo amarelo claro, sombra, bola próxima, movimento,
ausência, fechamento e negativos. Firmware hash preservado. Janela OBS v4
reaberta para teste do usuário; validar nova gravação crua e iluminação diferente.

## Regressão v4 e correção v5

Screenshot posterior confirmado: v4 selecionou mão, embora bola estivesse
visível. A união das máscaras cor forte/sombra conectou regiões; contorno maior
teve solidez 0,62 e foi rejeitado, restando região circular da mão. v5 extrai
contornos dessas máscaras separadamente, com leve preferência por cor forte,
sem unir regiões. Amarelo e sombra continuam candidatos, evitando veto rígido
que piorava a amostra do vídeo. Nome do perfil aparece no título e nos logs.

No crop do screenshot x=0/y=31/640×444, nova medida (422,01;252,72), raio
37,15 px na bola por inspeção visual. Nas mesmas 18 amostras JPEG: 14 TP,
0 FP, 2 FN, 2 TN; erro médio centro 10,28 px, raio 7,66 px, mediana 1,66 ms.
O raio médio piorou frente aos 4,91 px do v4 nessa amostra: não afirmar melhora
universal de precisão. Correção deste caso não demonstra estabilidade geral.
71 testes passaram, incluindo ponte escura ligando bola a região circular da
mão. OBS v5 reaberto. Relatório v5 de amostras em artifacts/live/; vídeo completo
e métricas de 2870 crops acima pertencem ao v4, não foram repetidos para v5.
`scripts/validate_live_video.py` agora registra o perfil atual e exporta
`live-demo.mp4`; o comando reproduz a versão atualmente instalada.

## v5 continua reprovada em cenário novo

Screenshot `codex-clipboard-70a85048-5953-4ef4-a543-3694ad489bbb.png` confirma
falso alvo na mão. Reproduzido **sem tracker**, crop x=0/y=31/640×444:
medida (452,14;402,89), raio 34,55 px. Bola visível aproximadamente (409;290).
Portanto, remover referência temporal ou aguardar aquisição não resolve.
Discos interiores inspecionados: bola HSV mediano (14;187;243), mão
(11;182;197); intervalos de hue/saturação se sobrepõem. Seleção por área/forma
e máscaras de cor pode favorecer pele, mesmo sem movimento.
Não considerar v5 estável ou validada para uso. Nenhuma versão v6 aplicada
a partir deste screenshot. Próximo passo: ampliar avaliação com os casos
reprovados recebidos e negativos de mão; reservar dados antes de ajuste e
validar aparência/seleção conjuntamente. Mais limiares isolados não provaram
generalização; avaliar abordagem de aparência aprendida se o baseline continuar
falhando. Métricas das 18 amostras anteriores não cobrem estes falsos alvos.
M4 físico ainda depende da webcam na Pi. Reconexão, fila limitada de aquisição,
supervisão de read() bloqueado e expiração até a apresentação ainda não implementadas.
Se o backend bloquear read(), a janela pode ficar sem resposta; não use este
ensaio para controle. Logs e captura diagnóstica ficam em runs/, fora do Git.
