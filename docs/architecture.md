# Arquitetura inicial

## Fluxo e responsabilidades

```text
CLI → Camera.read() → Frame → validade temporal → BallDetector → BallObservation
                         ↓                              ↓
                   captura BGR                   avaliação opcional
                                                        ↓
                                                   registro JSONL
```

- `models.py`: contratos e validação de metadados, imagens e observações.
- `cameras.py`: contrato `Camera`, erro de aquisição e câmera sintética com perturbações M2.
- `perception.py`: reconhecimento do candidato somente a partir do frame.
- `pipeline.py`: rejeição por idade, coordenação, métricas e encerramento da fonte.
- `telemetry.py`: serialização JSONL e descarga dos eventos.
- `__main__.py`: argumentos, arquivo de saída e composição do cenário M1.
- `experiments.py`: comparação dos cenários M2, logs separados e resumo com status.
- `sectors.py`: ciclos sincronizados de câmeras por setor e saída no terminal.
- `communication.py`: mensagens JSON por linha em PySerial, com loopback de bancada.
- `m3.py`: vídeos anotados, terços da imagem e reprodução opcional com Tk.
- `evaluate_m3.py`: anotações externas, comparação de perfis e métricas espaciais.

Um processo local é suficiente neste milestone. Não há serviços ou rede.
`Camera` é um `Protocol` de Python: uma classe que forneça `read()` e `close()`
atende ao contrato sem precisar herdar de uma classe base. Essa interface foi
solicitada para permitir a troca da simulação por câmera USB. Os testes usam
outra fonte controlada para verificar que o pipeline não depende da simulação.

`read()` retorna um frame, `None` para fim normal ou levanta `CameraError` para
falha de aquisição. Após encerrada, a câmera simulada recusa novas leituras.
O pipeline chama `close()` em um bloco `finally`, inclusive em erro de escrita ou
percepção. A fonte é responsável por traduzir falhas de aquisição em `CameraError`.
Erros inesperados continuam visíveis, sem serem convertidos em detecções ausentes.

## Invariantes

- Imagem BGR `uint8`, com três canais e dimensões não vazias.
- A fonte entrega um buffer que permanece válido durante o processamento;
  o detector não o modifica. A dataclass congelada não torna o array imutável.
- Origem do frame identificada por `camera_id`; sequência e timestamp não negativos.
- Timestamp da observação é o de captura, preservado pelo detector.
- Entrega opcional (`received_timestamp_ns`) usa o relógio da captura e não pode
  antecedê-la. Uma fonte sem esse metadado continua compatível com M1, mas não pode
  usar a política de idade. O pipeline recusa avaliar idade desconhecida.
- Ausência de bola usa coordenadas `None` e confiança zero.
- Detecção usa coordenadas finitas e não negativas; o detector calcula o centro
  dentro da imagem. Confiança finita entre zero e um.
- Falha de aquisição é distinta de ausência de bola.
- O detector não recebe o ground truth. A CLI o entrega separadamente ao avaliador.
- Na avaliação, ground truth e frames recebidos precisam ter o mesmo comprimento
  e sequência contígua começando em zero; rejeições por idade preservam o alinhamento.
- `run_summary` só é escrito após consumo e avaliação normais da sequência.
- Resultados existentes não são sobrescritos.
- Idade acima do limite é registrada em `frame_rejected`, sem chamar o detector.
  Igualdade com o limite é aceita. Rejeições não entram nas métricas de percepção.
- Falha da fonte registra `camera_error` com resumo parcial e encerra o pipeline.
  Nenhuma métrica é extrapolada para frames não recebidos.

As coordenadas são da imagem, não do campo nem do referencial do robô. Para obter
ângulo ou posição física, precisaremos da calibração e geometria de montagem.

## Escolhas e alternativas

**Python, NumPy e OpenCV headless:** permitem operações de imagem bem conhecidas.
A variante headless evita dependências de interface gráfica, pois o M1 grava
resultados no terminal e em arquivo. A alternativa seria implementar operações
de imagem manualmente ou usar OpenCV com GUI; nenhuma ajuda a validar este M1.
O custo é instalar pacotes binários, cuja compatibilidade será conferida nas Pis.

**Limiar HSV e contornos:** baseline simples de inspecionar. O maior contorno com
área ≥ 50 pixels quadrados e circularidade ≥ 0,65 vence. Limites HSV: H de 5 a 25,
S de 120 a 255 e V de 100 a 255, na escala OpenCV. Não usamos aprendizado de
máquina porque ainda não há dataset real ou evidência de necessidade. Os limiares
pertencem ao cenário sintético, não são uma calibração da bola real.

**JSON Lines:** legível, incremental e suficiente para os primeiros experimentos.
Não precisamos de banco de dados. Os registros crescem linearmente; retenção e
rotação serão consideradas antes de execuções contínuas no hardware.

**Unittest:** biblioteca padrão, sem framework de testes adicional. Os testes
verificam resultados, falhas e contratos, incluindo fontes e imagens independentes
da geração do cenário principal.

## Tempo, distribuição e evolução

O tempo simulado é `sequence * 1_000_000_000 // 30`, no domínio `simulation`.
`perf_counter_ns()` mede apenas a duração local do detector. Não subtraímos
timestamps de domínios diferentes para inventar latência.

No M2, entrega = captura + atraso configurado. A política de idade pertence ao
pipeline, enquanto a geração do atraso pertence à fonte. São relógios virtuais,
sem espera real ou modelo de filas. A verificação é feita na entrega; não inclui
o tempo posterior de processamento ou eventual comunicação ao robô.

O comparador usa limite experimental de 100 ms. `run_start` inclui parâmetros de
simulação, semente e versões Python/NumPy/OpenCV. Ruído gaussiano é independente
por canal BGR, limitado a [0, 255]. A oclusão cobre da esquerda para a direita uma
fração da largura de 25 pixels da bola, arredondada para cima. A resposta conhecida
permanece separada dos pixels perturbados.

A extração de `_Metrics` centraliza os resultados normais e parciais. Todos os
frames recebidos entram na contagem de disponibilidade; somente frames processados
entram em TP/FP/FN/TN. Assim, descarte de dados não aparenta melhora na detecção.

Em `camera_loss`, o comparador continua após a falha planejada e identifica o
resultado como parcial. Uma falha de fonte em outro cenário aborta o comparador.
Não há reconexão automática nem política de continuidade de motores nesta etapa.

Fontes futuras declararão seus relógios e limitações de captura. Multi-câmera
exigirá identificação, sincronização e política para descartar frames antigos,
além de filas limitadas para não acumular latência.

Fusão e interface de controle do robô serão implementadas nas etapas de hardware.
O GIGA continuará dono do controle. A primeira integração deverá
receber dados apenas para observação; influência nos motores exige definição
explícita de prioridade, expiração e comportamento em falha.

No M3, `RecordedVideoCamera` atende ao mesmo contrato. Não fornece idade de
hardware; seus timestamps são posições do decoder no domínio `recorded_video`.
O número de frames informado pelo arquivo delimita o fim normal; falha antecipada
e mudança de dimensões são erros. Arquivos sem FPS/contagem válidos são recusados.

`BallDetector(recorded=True)` usa o perfil HSV M3 e redução de resolução,
morfologia e forma convexa. `BallTracker` mantém uma referência de posição/raio
por até dois segundos do vídeo, usando-a somente para filtrar os candidatos atuais.
Não há previsão, suavização com atraso ou coordenadas repetidas quando a medida
é perdida. Medidas cortadas nas bordas horizontais não atualizam o raio de referência.
O perfil padrão do detector preserva M1/M2; `ball_radius` é um campo opcional
adicionado a `BallObservation` e aos eventos, compatível com consumidores que
aceitam campos adicionais. A confiança continua uma medida de forma.

A anotação visual e os limiares de avaliação ficam fora do detector. O avaliador
verifica SHA-256 e dimensões, percorre a sequência inteira para reproduzir o estado
do tracker e pontua somente os frames anotados. Um alvo fora da tolerância espacial
conta FP e FN. A avaliação M3 é diferente da avaliação de presença M1/M2.

A reprodução Tk é opcional, sem dependência de OpenCV GUI. Aguarda timestamps do
vídeo e não mantém fila de imagens processadas. Se a máquina ficar lenta, a
reprodução também fica lenta: não há promessa de tempo real estrito ou captura
USB. A exportação é CFR no FPS médio da fonte, sem áudio; os JSONL preservam os
timestamps originais de mídia. Não medir idade usando `perf_counter - media_time`.

TCP e UDP entre Pis continuam opções a avaliar. A pedido do FabLab, foi adicionada
saída serial PySerial opcional, exercitada em loopback. O formato JSON por linha é
experimental; não há receptor implementado no GIGA nem integração de motores.
Também não existe garantia de tempo real neste pipeline Python.

## Extensão de setores

A montagem de cada câmera determina F/D/E/A. `analyze_frame()` passou a ser o ponto
comum de validade e detecção para fontes individuais e para ciclos por setor.
Isso preserva a política M2 sem duplicar guardas ou acoplar o detector ao hardware.
O pipeline de setores mantém todas as detecções válidas e declara a cobertura local;
não escolhe prioridade nem tenta fundir dados entre relógios de placas diferentes.

Ausência de bola e indisponibilidade são estados distintos. Falha de fonte/serial
encerra a execução. O receptor futuro precisará expirar o último dado recebido
quando o emissor parar. Consulte [os estados e a comunicação de bancada](sectors-and-serial.md).
