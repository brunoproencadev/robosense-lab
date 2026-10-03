# Validação M2 — 03/10/2026

## Implementação

O M2 acrescenta ruído gaussiano com semente, oclusão de largura configurável,
perda terminal da fonte e atraso virtual. Não altera o detector HSV do M1 nem
o firmware GIGA. O pipeline calcula idade captura/entrega no mesmo relógio,
rejeita frames antigos antes da percepção e mantém as métricas de disponibilidade
separadas das métricas de detecção.

Foi mantido o significado do campo `frames`: frames efetivamente processados.
`frames_received`, `stale_frames`, tempos de entrega e `partial_summary` são
extensões do registro. Eventos antigos permanecem; o M2 acrescenta `frame_rejected`.
Consumidores devem aceitar campos adicionais e distinguir os tipos de evento.

## Ambiente e execução

- Windows local; Python 3.14.5.
- NumPy 2.5.3; OpenCV runtime 4.14.0 (pacote headless já instalado).
- Nenhuma nova dependência foi adicionada.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m robosense_lab.experiments --frames 60 --seed 42 --output-dir runs/m2-validation
```

**37 testes passaram** em 0,804 s naquela execução: os 19 do M1 e 18 do M2.
O comparador concluiu os sete cenários e escreveu os logs e `summary.json`.
O resultado da perda planejada permanece identificado como `camera_error`.

Os logs completos estão localmente em `runs/m2-validation/`, ignorados pelo Git.
[artifacts/m2-summary.json](../artifacts/m2-summary.json) é uma cópia do resumo
observado, preservada junto com este relatório.

## Resultados observados

Todos os cenários planejaram 60 frames com 48 bolas fisicamente presentes e
12 ausências, exceto a perda da câmera, que impediu obter a segunda metade.
O limite experimental de idade foi 100 ms, inclusive.

| Cenário | Recebidos / processados | Rejeitados por idade | TP / FN / FP / TN | Recall | Erro médio do centro |
| --- | --- | ---: | --- | ---: | ---: |
| Baseline M1 | 60 / 60 | 0 | 48 / 0 / 0 / 12 | 100% | 0 px |
| Ruído, desvio padrão 45, semente 42 | 60 / 60 | 0 | 24 / 24 / 0 / 12 | 50% | 0,108 px |
| Oclusão de 50% da largura | 60 / 60 | 0 | 48 / 0 / 0 / 12 | 100% | 5,394 px |
| Oclusão completa | 60 / 60 | 0 | 0 / 48 / 0 / 12 | 0% | Não calculável |
| Perda no índice 30 | 30 / 30 | 0 | 24 / 0 / 0 / 6 | 100% no trecho observado | 0 px |
| Atraso virtual de 50 ms | 60 / 60 | 0 | 48 / 0 / 0 / 12 | 100% | 0 px |
| Atraso virtual de 200 ms | 60 / 0 | 60 | 0 / 0 / 0 / 0 | Não calculável | Não calculável |

TP/FP/FN/TN medem presença, sem exigir um limite de acerto espacial. Por isso,
detectar uma bola parcialmente coberta ainda pode contar como TP mesmo com centro
deslocado. O erro de centro é calculado somente nos TPs e precisa ser lido junto
com recall: os 0,108 px do ruído não incluem as 24 bolas perdidas.

Oclusão completa mantém a bola no ground truth físico, mas remove sua evidência
visual. Os 48 FNs são uma limitação esperada de percepção por uma imagem, não prova
de que seria possível detectá-la totalmente escondida.

Na perda da câmera, o JSONL termina em `camera_error`, sem resumo de sucesso.
Os 30 frames não recebidos não contam como FN ou TN. Em atraso de 200 ms, todos
os frames terminam em `frame_rejected`; não há observação de bola, nem tempo de
detector, precisão ou recall calculados. O status `completed` significa que a
sequência foi consumida normalmente, mesmo se nenhum dado foi utilizável.

## Provas automatizadas

- Pixels e métricas do cenário padrão permanecem equivalentes ao M1.
- Mesmo ruído/semente reproduz imagens; outra semente altera os pixels.
- Oclusão modifica pixels e preserva a posição física conhecida.
- Captura não é reescrita para esconder o atraso; entrega precedendo captura é inválida.
- Idade exatamente no limite é aceita; acima dele rejeita antes do detector.
- Rejeições no meio da sequência não deslocam a comparação com ground truth.
- Fonte sem timestamp de entrega não pode aplicar limite de idade.
- Falha terminal produz métricas somente do trecho observado e fecha a fonte.
- Logs e resumo preservam configuração e versões; pastas existentes não são sobrescritas.
- Reexecução com mesmos parâmetros reproduz resultados, exceto duração medida.
- CLI rejeita parâmetros inválidos, inclusive NaN, infinito e índice de perda fora da sequência.

## Limites e próxima etapa

Os resultados são de uma única configuração sintética e semente. Não representam
robustez na Infrared League, benchmark de Raspberry Pi ou latência física. O
atraso virtual testa validade temporal na entrega, sem modelo de filas, rede,
sincronização entre placas ou tempo de reação do robô. O limite de 100 ms é
experimental e precisará de justificativa com hardware e controle reais.

O M2 não adiciona recuperação de câmera, tracking, fusão ou integração de motores.
A demonstração visual M1 continua sendo o cenário limpo. A próxima etapa é M3:
gravações reais, anotações e escolha do baseline com evidência da bola da equipe.
