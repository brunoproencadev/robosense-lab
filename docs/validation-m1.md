# Validação M1 — 03/10/2026

## Ambiente observado

- Windows, execução local em `D:\projects\RoboSense Lab`.
- Python 3.14.5, ambiente virtual `.venv`.
- NumPy 2.5.3.
- opencv-python-headless 4.14.0.94.
- setuptools 84.0.0.
- robosense-lab 0.1.0 instalado em modo editável.

Python 3.12 foi listado no computador, mas sua execução retornou acesso negado.
A validação usou o Python 3.14 disponível. A instalação das dependências no PyPI
precisou de autorização de rede do ambiente. O projeto foi instalado com
`pip install --no-build-isolation -e .` após a instalação de setuptools.

## Testes executados

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m robosense_lab --frames 60 --output runs/m1-validation.jsonl
.\.venv\Scripts\python.exe -m pip check
```

Resultados observados:

- 19 testes passaram, em 0,182 s naquela execução.
- `pip check`: nenhuma dependência incompatível encontrada.
- A CLI concluiu normalmente e produziu `runs/m1-validation.jsonl`.
- A suíte verifica que o JSONL contém início, observações e resumo, e que a CLI
  recusa sobrescrever um arquivo existente.
- A suíte cobre determinismo, contratos inválidos, alvo independente, ausência,
  cor errada, alvo pequeno/alongado, seleção entre candidatos e métricas com erros.
- As falhas de fonte, escrita e detector encerram a fonte. Falha de aquisição
  gera evento próprio e não gera resumo de sucesso.
- O sketch foi comparado textualmente com o trecho do anexo: idêntico.

## Execução de 60 frames

| Métrica | Resultado observado |
| --- | ---: |
| Frames processados | 60 |
| Verdadeiros positivos | 48 |
| Verdadeiros negativos | 12 |
| Falsos positivos | 0 |
| Falsos negativos | 0 |
| Precisão de presença | 1,0 |
| Recall de presença | 1,0 |
| Erro médio do centro | 0,0 px |
| Tempo médio apenas do detector | 0,1747466667 ms |

Os registros em `runs/` são artefatos locais ignorados pelo Git. Este relatório
preserva os resultados observados; uma nova execução deve usar outro nome de saída.
O tempo indicado é uma única observação, não um benchmark representativo.

## Limitações e próximo passo

Resultados válidos somente para o cenário sintético simples. Não demonstram
capacidade de detectar a bola real, desempenho no Raspberry Pi, latência ponta a
ponta ou segurança de integração nos motores. Não houve teste em Linux, webcam,
Arduino ou robô; o firmware não foi compilado.

O M1 encerra com o caminho local completo validado. O próximo milestone é M2:
cenários controlados de ruído, oclusão, perda de câmera e atraso. Em paralelo, a
equipe pode coletar vídeos da bola real para reduzir a incerteza óptica do M3.
