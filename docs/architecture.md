# Arquitetura inicial

## Fluxo e responsabilidades

```text
CLI → Camera.read() → Frame → BallDetector.detect() → BallObservation
                         ↓                              ↓
                   captura BGR                   avaliação opcional
                                                        ↓
                                                   registro JSONL
```

- `models.py`: contratos e validação de metadados, imagens e observações.
- `cameras.py`: contrato `Camera`, erro de aquisição e câmera sintética.
- `perception.py`: reconhecimento do candidato somente a partir do frame.
- `pipeline.py`: coordenação, métricas e encerramento da fonte.
- `telemetry.py`: serialização JSONL e descarga dos eventos.
- `__main__.py`: argumentos, arquivo de saída e composição do cenário M1.

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
- Ausência de bola usa coordenadas `None` e confiança zero.
- Detecção usa coordenadas finitas e não negativas; o detector calcula o centro
  dentro da imagem. Confiança finita entre zero e um.
- Falha de aquisição é distinta de ausência de bola.
- O detector não recebe o ground truth. A CLI o entrega separadamente ao avaliador.
- Na avaliação do M1, ground truth e frames precisam ter o mesmo comprimento e
  sequência contígua começando em zero; divergências encerram a execução com erro.
- `run_summary` só é escrito após consumo e avaliação normais da sequência.
- Resultados existentes não são sobrescritos.

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

Fontes futuras declararão seus relógios e limitações de captura. Multi-câmera
exigirá identificação, sincronização e política para descartar frames antigos,
além de filas limitadas para não acumular latência.

Tracking, fusão, comunicação e interface do robô serão módulos próprios quando
implementados. O GIGA continuará dono do controle. A primeira integração deverá
receber dados apenas para observação; influência nos motores exige definição
explícita de prioridade, expiração e comportamento em falha.

TCP e UDP entre Pis, e serial USB/UART com o GIGA, continuam opções a avaliar.
Nenhum transporte foi escolhido ou implementado. Também não existe garantia de
tempo real neste pipeline Python.
