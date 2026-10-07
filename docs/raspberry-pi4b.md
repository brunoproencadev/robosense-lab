# Preparação para Raspberry Pi 4B

## Alvo

Atualização 07/10: ensaio de câmera/servos relatado pelo usuário, fonte recuperada
e integração preparada. Para arquivo único `.pyz`, calibração e sinais pan/tilt,
consulte [validation-m4.md](validation-m4.md). O relato não valida a suíte ARM,
desempenho ou recuperação do projeto integrado.

Raspberry Pi OS **64 bits**, arquitetura `aarch64`, Python **3.11 ou superior**.
Use o Python fornecido pela distribuição; não é necessário levar o Python 3.14
do Windows. O mínimo anterior de 3.12 foi reduzido para 3.11 porque o código não
usa recursos exclusivos de 3.12, permitindo também distribuições com Python 3.11.

A alteração é apenas de compatibilidade permitida. O código foi executado
localmente em Windows/Python 3.14.5. ARM64/Python 3.11 ainda precisa da execução
dos testes. Python e dependências no ambiente Windows continuam os mesmos.

Sistemas Raspberry Pi OS de 32 bits não são o alvo validado para os pacotes
binários escolhidos. Confira antes de instalar:

```bash
uname -m
python3 --version
```

Esperado: `aarch64` e Python >= 3.11. Também será necessário um microSD com espaço,
fonte adequada e acesso à Internet para instalar os pacotes.

## Instalação na Pi

```bash
sudo apt update
sudo apt install python3-venv python3-pip git
git clone https://github.com/brunoproencadev/robosense-lab.git
cd robosense-lab
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . --only-binary=numpy,opencv-python-headless
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m robosense_lab.sectors --frames 6 --serial-port loop:// --output runs/pi-loopback.jsonl
```

Estas instruções devem usar uma revisão que contenha `robosense_lab.sectors`.
O ambiente `.venv` deve ser criado de novo em cada Pi; não copie o ambiente Windows.
Não use `sudo pip`, e execute a aplicação como usuário comum. A instalação exige
wheels de NumPy/OpenCV para evitar compilação longa e consumo alto de memória na
placa. Se não houver wheel compatível, preserve a mensagem de erro e confira OS,
arquitetura e Python; não retire o limite automaticamente para compilar tudo.

## Duas câmeras por placa: preparação lógica

Depois da demonstração de quatro setores, cada placa pode exercitar seu subconjunto:

```bash
# Exemplo de Pi A: frente e direita, ainda simuladas
.venv/bin/python -m robosense_lab.sectors --sectors FD --frames 6 --output runs/pi-a.jsonl
# Exemplo de Pi B: esquerda e atrás, ainda simuladas
.venv/bin/python -m robosense_lab.sectors --sectors EA --frames 6 --output runs/pi-b.jsonl
```

A escolha FD/EA é um exemplo de atribuição, não uma regra da montagem. Confirme
a posição física das câmeras com Antoni. Os registros explicitam quais setores
estão cobertos; nenhum subconjunto representa sozinho o campo de visão completo.
Não há comunicação entre placas ou aquisição USB nesta etapa.

## Porta serial física, quando o teste de bancada estiver preparado

Conecte a placa por USB e identifique a porta:

```bash
ls -l /dev/serial/by-id/
```

Prefira esse caminho persistente a um número variável como `/dev/ttyACM0`.
Se houver erro de permissão, confira o grupo dono da porta. Em Raspberry Pi OS,
normalmente é `dialout`; se for esse o caso, um administrador pode executar:

```bash
sudo usermod -aG dialout "$USER"
```

Saia da sessão e entre novamente para aplicar a associação. Não torne a porta
gravável por todos e não execute a aplicação como root. O nome do dispositivo,
permissões e comportamento ao abrir a porta devem ser confirmados na bancada.

A opção `--serial-port /dev/serial/by-id/...` permite enviar mensagens depois que
o caminho e o receptor forem preparados. No Windows, o equivalente é uma porta
como `COM3`. O firmware GIGA atual não interpreta esse JSON: não habilite controle
de motores baseado nessa comunicação antes da etapa de integração e expiração.
`loop://` é a opção já exercitada, sem placa física.

## Provas disponíveis e limites

Foi feita resolução e download de wheels para Linux ARM64/Python 3.11:

- NumPy 2.4.6, CPython 3.11, manylinux 2.27/2.28 aarch64.
- OpenCV headless 4.14.0.94, ABI3, manylinux 2.28 aarch64.
- PySerial 3.5, wheel Python independente de plataforma.

Isso confirma disponibilidade das distribuições, não funcionamento do código ou
desempenho físico. Arquivos baixados estão em `runs/pi4b-wheels/`, ignorados pelo Git.
Os 11 módulos de `src` também passaram pela análise de sintaxe usando a gramática
Python 3.11 no host. Isso não equivale a executar a suíte nesse Python.

O workflow `.github/workflows/tests.yml` prepara verificações em Linux x64/Python
3.11, Linux ARM64/Python 3.11 e Windows/Python 3.14. Ele ainda não foi executado
nesta etapa. Mesmo um resultado ARM64 de CI não substitui teste de USB, temperatura,
alimentação e FPS na Pi 4B. A bola real continua dependendo do dataset M3.
