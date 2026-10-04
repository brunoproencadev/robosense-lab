# Setores e saída PySerial de bancada

## Plano aplicado

1. Identificar as fontes por setor e simular visibilidade independente.
2. Reusar `BallDetector` e a verificação de idade do M2.
3. Imprimir todos os setores detectados, sem escolher prioridade.
4. Acrescentar PySerial opcional, testável com `loop://`.
5. Preparar instalação Linux ARM64/Python 3.11 e verificações de compatibilidade.

`SimulatedCamera` recebeu identidade e lista de frames visíveis opcionais. Sem
esses argumentos, os pixels e o comportamento padrão M1/M2 continuam iguais.
`analyze_frame()` centraliza a detecção e a rejeição temporal para ambos os
pipelines. O detector nunca recebe os setores esperados ou a posição verdadeira.

## Execução

Após atualizar a instalação (`python -m pip install -e .` dentro do ambiente), use:

```powershell
.\.venv\Scripts\python.exe -m robosense_lab.sectors --frames 6 --output runs/setores.jsonl
.\.venv\Scripts\python.exe -m robosense_lab.sectors --frames 6 --serial-port loop:// --output runs/setores-serial.jsonl
```

No Linux, substitua o executável por `.venv/bin/python`. Escolha nomes novos para
repetir execuções. Nenhuma porta serial é aberta se `--serial-port` for omitido.

O roteiro repete seis ciclos: frente, direita, esquerda, atrás, nenhuma bola e
sobreposição frente/direita. São quatro imagens independentes de 320 × 240 por
ciclo, analisadas pelo OpenCV. O resultado observado foi:

```text
F
D
E
A
SEM_BOLA
F D
```

O setor representa a montagem atribuída à câmera, não a coordenada do pixel. Um
candidato em qualquer parte do frame da câmera frontal conta como `F`. Isso não
é localização geométrica ou fusão entre câmeras.

## Estados e cobertura

- `detected`: um ou mais setores detectaram um candidato em frames válidos.
- `no_ball`: nenhuma câmera local detectou candidato; imprime `SEM_BOLA`.
- `unavailable`: alguma câmera local tem frame antigo; imprime `SEM_DADOS` e
  não apresenta setores como uma observação válida. Os detalhes ficam no JSONL.

Uma falha de aquisição ou escrita serial aborta a execução, registra erro e não
produz resumo de sucesso. Nenhuma direção anterior é repetida ou armazenada como
substituta. O encerramento normal das fontes precisa ocorrer no mesmo ciclo.

`--sectors FD` simula apenas frente/direita; `--sectors EA`, esquerda/atrás. Esse
é um possível arranjo local para duas Pis, a confirmar pela montagem. Toda
mensagem declara `observed_sectors`: `no_ball` em uma Pi não afirma ausência nas
câmeras da outra. Ainda não há comunicação, sincronização ou agregação entre Pis.

O demonstrador consome fontes sincronizadas, com mesmos índices, timestamps de
captura e domínio de relógio; combinações diferentes são recusadas. A aquisição
real e a política para alinhar câmeras assíncronas serão tratadas no milestone de
hardware. O atraso continua virtual, como no M2.

## Formato serial experimental

O terminal imprime as letras. A serial usa **JSON ASCII por linha, terminado em LF**:

```json
{"schema_version":1,"sequence":0,"timestamp_ns":0,"clock_domain":"simulation","observed_sectors":["F","D","E","A"],"status":"detected","sectors":["F"]}
```

Na sobreposição, `sectors` é `["F","D"]`. Em ausência/indisponibilidade, a lista
é vazia, mas `status` distingue os casos. Sequência e captura não são reescritas
para esconder atraso. A ordem das letras é F/D/E/A, sem significado de prioridade.

PySerial usa baudrate configurável, padrão 115200, e timeout de leitura/escrita de
1 s. Escrita parcial é erro. Em `loop://`, o emissor também lê e confere o eco dos
bytes enviados. Em porta física, escrita concluída não comprova recepção no GIGA;
não existe confirmação ou retry nesta etapa. Somente portas locais e `loop://`
são aceitos, sem transporte serial por rede.

Este formato é de bancada. O baseline GIGA não tem parser para ele e não foi
alterado. Antes de usar dados no controle, será necessário implementar e validar
o receptor, limites de mensagem, expiração por tempo local de recepção e regra
para múltiplos setores. Um timestamp de `simulation` não é comparável ao relógio
do GIGA. Se o emissor parar ou desconectar, o receptor futuro deve expirar os dados;
um último `F` não pode permanecer válido indefinidamente.

## Validação local — 03/10/2026

- Windows/Python 3.14.5, PySerial 3.5, NumPy 2.5.3 e OpenCV 4.14.0.
- 50 testes passaram: 37 existentes e 13 de setores/serial.
- Execução real de seis ciclos com `loop://`: eco conferido byte por byte.
- Sem bola e sobreposição produziram os estados esperados, sem prioridade inventada.
- Testes cobrem câmera antiga, relógios distintos, falha de fonte/serial, escrita
  parcial, eco incorreto, cobertura local e proteção de arquivos existentes.
- Instalação editável atualizada; `pip check` não encontrou requisitos quebrados.
- O arquivo `runs/sectors-validation.jsonl` registra a demonstração local.

Não foi aberta porta física nem executado código em Raspberry Pi ou GIGA. As
quatro webcams reais e a detecção da bola infravermelha continuam pendentes.
