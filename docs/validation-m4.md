# M4 — ensaio de escola recuperado, pan/tilt e transferência

## Estado em 07/10/2026

Bruno relata câmera USB/detecção e servos posicionais funcionando na Pi4B.
O arquivo recebido foi preservado em `references/tracking_bola_school.py`;
hash e origem no README desse diretório. Não foi necessário refazer o trabalho.
A foto mostra interface na Pi, máscara com pele e aviso de baixa tensão.
Python 3.13.5 aparece na tela; distribuição, arquitetura, webcam, exposição e
modelo dos servos ainda precisam ser registrados na escola.

~15 FPS e melhora de ~80% com luva branca são estimativas do usuário, sem
medição/avaliação anotada. Não são resultados validados. A luva altera o fundo
e pode reduzir a confusão de cor com pele; FPS sozinho não explica esse efeito.
M4 começou como ensaio físico **relatado**, mas não está concluído: faltam
medidas de aquisição, recuperação, temperatura, alimentação e teste do projeto
integrado na Pi. Os testes desta entrega ocorreram em Windows, sem GPIO físico.

## Plano e implementação

1. Recuperar fonte/HSV (H=3–25, S>=150, V>=70, processamento 320), mantendo
   `Camera -> Frame -> Detector -> BallObservation`. Perfil `school-hsv-v1`
   selecionado por `--detector hsv`; não substitui o v5 por padrão.
2. Pan passa a sinal -1, inverso ao +1 do arquivo recebido. Tilt só integra erro
   **abaixo** do centro e nunca desfaz a inclinação para procurar alvo acima.
   `--tilt-down-sign -1` define diminuição de pulso como descida proposta.
3. GPIO BCM 18 pan (pino físico 12), BCM 19 tilt (pino físico 35), via pigpio
   local; rodas/GIGA permanecem separados. Servos desligados por padrão.
4. Logs novos, prévia Tk opcional, modo contínuo headless e arquivo `.pyz` com
   código Python do projeto. Nenhuma cópia do venv Windows ou GUI OpenCV exigida.

Sinais físicos dependem da montagem: -1 é a correção lógica proposta com base
no relato, não uma calibração física comprovada. Neutro lógico é 1500 us.
Pan fica entre 1200–1800; tilt fica entre 1200–1500 para sinal -1 ou
1500–1800 para sinal +1. Velocidade máxima 90 us/s, zona morta 8%, passo temporal
máximo 0,1 s. Antes de armar, confirme que neutro/limites não forçam a montagem.
A primeira medida válida emite a referência neutra; sem encoder, a posição
física inicial não é conhecida e esse primeiro posicionamento pode mover o eixo.
A restrição de não subir vale para avanços lógicos **a partir dessa referência**.
Somente descer significa que uma bola acima do centro não será centralizada
verticalmente. Recomeçar o programa reinicia a referência, não lê posição real.

Perda, dados futuros/antigos (>100 ms), relógio incompatível ou sequência
repetida desligam ambos os pulsos. Watchdog em thread confere a cada 50 ms:
após 500 ms sem atualização válida, tenta desligar ambos, mesmo se read() bloquear.
Falhas GPIO são propagadas; fechamento tenta zero nos dois pinos e desconecta.
Zero PWM não equivale a freio/posição fixa; a câmera pode ceder com a carga.
Watchdog depende de Python/daemon/IPC funcionando; não substitui corte físico
de alimentação. Falso positivo do detector ainda pode mover a câmera.

## Instalação e transferência

Recomendado com Internet na Pi:

```bash
git clone https://github.com/brunoproencadev/robosense-lab.git
cd robosense-lab
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[pi-servos]'
# Tk só se usar a janela; pigpiod deve ser o instalado/testado na escola.
sudo apt install python3-tk
sudo pigpiod -l
```

Se o serviço já estiver rodando, não abra uma segunda instância. O pacote Python
pigpio não instala o daemon; confirme a instalação local da escola. Se `pigpiod`
não existir, registre OS/arquitetura e a disponibilidade do pacote antes de
instalar ou trocar bibliotecas. Aplicação roda como usuário comum, não com sudo.

Para transferir **um arquivo**, baixe `artifacts/pi/robosense-pi.pyz` do GitHub
ou gere a partir da revisão atual:

```powershell
.\.venv\Scripts\python.exe scripts\build_pi_app.py --output runs/pi-NOVO/robosense-pi.pyz
```

Na Pi, copie apenas o `.pyz` (não precisa extrair), crie venv e instale dependências:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install 'numpy>=2.2,<3' 'opencv-python-headless>=4.11,<5' 'pyserial>=3.5,<4' 'pigpio>=1.78,<2'
.venv/bin/python robosense-pi.pyz --help
```

O `.pyz` contém somente os módulos Python; não contém vídeos, datasets, pesos,
dependências ARM ou ambiente virtual. Regere quando alterar módulos de src;
o builder recusa sobrescrever resultados. O arquivo publicado nesta entrega
corresponde aos módulos desta revisão; teste de execução local não valida ARM.

## Ensaio na próxima visita

Primeiro **sem servos**, por 300 frames, pasta nova:

```bash
.venv/bin/python robosense-pi.pyz --device 0 --detector hsv --frames 300 --no-preview --output-dir runs/pi-hsv-NOVO
```

Para a janela omita `--no-preview`; Tk exige sessão gráfica. Para usar checkout,
troque `robosense-pi.pyz` por `-m robosense_lab.live`. HSV pode ser ajustado com
`--h-min`, `--h-max`, `--s-min`, `--v-min`. Perfil HSV usa imagem inteira;
`--roi-top` só pertence ao perfil live. Registrar comparação com/sem luva,
bola ausente, mão sozinha, sombra e fundo do campo; não validar só um cenário.

Depois confirme montagem, fonte dos servos, terra comum, neutro e limites.
Servos precisam de alimentação adequada ao seu modelo; não alimentá-los por
GPIO. Confira o aviso de baixa tensão da Pi e, na bancada, `vcgencmd get_throttled`;
registre o valor em vez de presumir que FPS/exatidão melhoraram.

Teste breve de direção com 30 frames e espaço livre no mecanismo:

```bash
.venv/bin/python robosense-pi.pyz --device 0 --detector hsv --servos --pan-sign -1 --tilt-down-sign -1 --frames 30 --output-dir runs/pi-direcao-NOVO
```

Se o movimento horizontal permanecer contrário, compare `--pan-sign 1`.
Se pulsos decrescentes fizerem tilt subir, **interrompa** e calibre `--tilt-down-sign 1`
antes de repetir. Não inverter o sinal durante movimento. Ctrl+C/Esc encerra;
verifique desligamento e posição segura. Só depois ampliar duração.

Logs incluem dimensões entregues, tempo de read(), detector, escrita dos servos,
intervalo de entrega ao host e pulsos lógicos. FPS do resumo é processamento no
host, não FPS óptico ou latência ponta a ponta. Verifique com/sem prévia e servos
para separar custos; não há pedido fixo de 15 FPS nem garantia de buffer aceito.
Tempo do detector Windows não é medida da Pi; TTL usa entrega ao host e não
detecta imagem velha já enfileirada no driver. Não há reconexão automática.

## Provas locais

- 81 testes passaram: HSV/escala/calibração, sentidos e limites, tilt sem retorno,
  dados repetidos/antigos/futuros, ausência, watchdog sem frames novos, falha de
  driver pigpio simulado, interrupção da CLI e fechamento.
- CLI HSV sem GPIO: seis frames sintéticos, cinco detecções, uma ausência, resumo
  e arquivos fechados. Isso não mede detecção em pixels reais da escola.
- `.pyz` construído/aberto com `--help`; fonte inexistente retornou código 1,
  mantendo a falha também no arquivo único. Nenhum pulso físico emitido.
- Módulos de src passaram por análise sintática para Python 3.11 no Windows.
- Firmware GIGA permanece com SHA-256
  `70fae2b690a0a7be5cc43dd1b7fb4a5fbfa22c7e4ac2ad20e71c7747c43b2513`.

Pendentes: confirmar sinais/limites na montagem, executar projeto na Pi,
medir alimentação/FPS/atrasos e obter gravação crua independente para melhorar
detecção. O relato da luva não comprova correção do detector.
