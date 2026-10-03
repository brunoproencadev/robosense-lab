#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BNO055.h>
#include <utility/imumaths.h>
#include <HTInfraredSeeker.h>

// =====================================================
// BNO055
// =====================================================

Adafruit_BNO055 bno = Adafruit_BNO055(55);

bool bnoCalibrado = false;
float anguloRobo = 0;
float offsetOrientacao = 0.0;
bool calibrar = false;

// =====================================================
// IR SEEKER
// =====================================================

int ballDirecao = 0;
int ballIntens = 0;

// =====================================================
// MOTORES
// =====================================================

#define M1_IN1 24
#define M1_IN2 22
#define M1_PWM 3

#define M2_IN1 38
#define M2_IN2 36
#define M2_PWM 8

#define M3_IN1 47
#define M3_IN2 45
#define M3_PWM 12

#define M4_IN1 26
#define M4_IN2 28
#define M4_PWM 4

#define MOTOR1_DIR 1
#define MOTOR2_DIR 1
#define MOTOR3_DIR 1
#define MOTOR4_DIR 1

#define COMPENSACAO_M4 1.4

// =====================================================
// BOTÃO
// =====================================================

#define botao 31

bool botaoAnterior = HIGH;
bool setado = false;

// =====================================================
// TSOPS
// =====================================================

const int NUM_TSOPS = 16;

const int TSOP_LIMIAR_MUDANCAS = 6;
const int TSOP_TEMPO_JANELA = 50;

int pinosTSOP[NUM_TSOPS] = {
  6, 42, 53, 44,
  7, 48, 5, 46,
  50, 52, 39, 41,
  51, 49, 43, 34
};

// =====================================================
// VELOCIDADES
// =====================================================

#define VELOCIDADE 150

// =====================================================
// CONTROLE INDIVIDUAL DOS MOTORES
// =====================================================

void motorWrite(int in1, int in2, int pwmPin, int speedValue) {

  speedValue = constrain(speedValue, -255, 255);

  if (speedValue > 0) {

    digitalWrite(in1, HIGH);
    digitalWrite(in2, LOW);

    analogWrite(pwmPin, speedValue);

  } 
  else if (speedValue < 0) {

    digitalWrite(in1, LOW);
    digitalWrite(in2, HIGH);

    analogWrite(pwmPin, -speedValue);

  } 
  else {

    digitalWrite(in1, LOW);
    digitalWrite(in2, LOW);

    analogWrite(pwmPin, 0);
  }
}

// =====================================================
// SET MOTOR
// =====================================================

void setMotor(int motor, int speedValue) {

  switch (motor) {

    case 1:

      motorWrite(
        M1_IN1,
        M1_IN2,
        M1_PWM,
        speedValue * MOTOR1_DIR
      );

      break;

    case 2:

      motorWrite(
        M2_IN1,
        M2_IN2,
        M2_PWM,
        speedValue * MOTOR2_DIR
      );

      break;

    case 3:

      motorWrite(
        M3_IN1,
        M3_IN2,
        M3_PWM,
        speedValue * MOTOR3_DIR
      );

      break;

    case 4:

      motorWrite(
        M4_IN1,
        M4_IN2,
        M4_PWM,
        speedValue * MOTOR4_DIR
      );

      break;
  }
}

// =====================================================
// PARAR
// =====================================================

void parar() {

  setMotor(1, 0);
  setMotor(2, 0);
  setMotor(3, 0);
  setMotor(4, 0);
}

// =====================================================
// MOVIMENTAR PARA FRENTE
// =====================================================

void moverFrente() {

  setMotor(1, -VELOCIDADE);
  setMotor(2, VELOCIDADE);
  setMotor(3, -VELOCIDADE);
  setMotor(4, VELOCIDADE * COMPENSACAO_M4);
}

// =====================================================
// MOVIMENTAR PARA ESQUERDA
// =====================================================

void moverEsquerda() {

  setMotor(1, VELOCIDADE);
  setMotor(2, VELOCIDADE);
  setMotor(3, -VELOCIDADE);
  setMotor(4, -VELOCIDADE * COMPENSACAO_M4);
}

// =====================================================
// MOVIMENTAR PARA DIREITA
// =====================================================

void moverDireita() {

  setMotor(1, -VELOCIDADE);
  setMotor(2, -VELOCIDADE);
  setMotor(3, VELOCIDADE);
  setMotor(4, VELOCIDADE * COMPENSACAO_M4);
}

// =====================================================
// MOVIMENTAR PARA TRÁS
// =====================================================

void moverTras() {

  setMotor(1, VELOCIDADE);
  setMotor(2, -VELOCIDADE);
  setMotor(3, VELOCIDADE);
  setMotor(4, -VELOCIDADE * COMPENSACAO_M4);
}

// =====================================================
// DIAGONAL PARA TRÁS E ESQUERDA
// =====================================================

void moverDiagonalTrasEsquerda() {

  setMotor(1, VELOCIDADE);
  setMotor(2, 0);
  setMotor(3, -VELOCIDADE);
  setMotor(4, 0);
}

// =====================================================
// DIAGONAL PARA TRÁS E DIREITA
// =====================================================

void moverDiagonalTrasDireita() {

  setMotor(1, 0);
  setMotor(2, -VELOCIDADE);
  setMotor(3, VELOCIDADE);
  setMotor(4, 0);
}

// =====================================================
// BNO055 - CALIBRAÇÃO
// =====================================================

void bno_calibrar() {

  Serial.println("Calibrando BNO055... aguarde.");

  uint8_t sys, gyro, accel, mag;

  while (true) {

    bno.getCalibration(
      &sys,
      &gyro,
      &accel,
      &mag
    );

    if (mag >= 2 && gyro >= 2) {

      bnoCalibrado = true;

      Serial.println(
        ">>> BNO055 CALIBRADO <<<"
      );

      break;
    }

    delay(200);
  }
}

// =====================================================
// ZERAR ORIENTAÇÃO
// =====================================================

void zerarOrientacao() {

  imu::Vector<3> euler =
    bno.getVector(
      Adafruit_BNO055::VECTOR_EULER
    );

  offsetOrientacao = euler.x();

  Serial.print(
    "Orientacao zerada: "
  );

  Serial.println(
    offsetOrientacao
  );
}

// =====================================================
// LER ORIENTAÇÃO
// =====================================================

float lerOrientacao() {

  imu::Vector<3> euler =
    bno.getVector(
      Adafruit_BNO055::VECTOR_EULER
    );

  float yaw =
    euler.x() - offsetOrientacao;

  while (yaw > 180.0) {
    yaw -= 360.0;
  }

  while (yaw < -180.0) {
    yaw += 360.0;
  }

  anguloRobo = yaw;

  return yaw;
}

// =====================================================
// ERRO ANGULAR
// =====================================================

float calcularErro(
  float anguloAtual,
  float anguloAlvo
) {

  float erro =
    anguloAlvo - anguloAtual;

  while (erro > 180) {
    erro -= 360;
  }

  while (erro < -180) {
    erro += 360;
  }

  return erro;
}

// =====================================================
// ROTAÇÃO BNO055
// =====================================================

#define ROT_KP 2.0
#define ROT_VELOCIDADE_MIN 56
#define ROT_VELOCIDADE_MAX 80
#define ROT_TOLERANCIA 4.0

int calcularRotacaoBNO() {

  float erro =
    calcularErro(
      lerOrientacao(),
      0
    );

  if (abs(erro) <= ROT_TOLERANCIA) {

    return 0;
  }

  int velocidadeRot =
    (int)(
      abs(erro) * ROT_KP
    );

  velocidadeRot =
    constrain(
      velocidadeRot,
      ROT_VELOCIDADE_MIN,
      ROT_VELOCIDADE_MAX
    );

  return (
    erro > 0
  )
    ? velocidadeRot
    : -velocidadeRot;
}

// =====================================================
// LEITURA DO IR SEEKER
// =====================================================

void lerSeeker() {

  InfraredResult resultado =
    InfraredSeeker::ReadAC();

  ballDirecao =
    resultado.Direction;

  ballIntens =
    resultado.Strength;

  Serial.print(
    "IR SEEKER | Direcao: "
  );

  Serial.print(
    ballDirecao
  );

  Serial.print(
    " | Intensidade: "
  );

  Serial.println(
    ballIntens
  );
}

// =====================================================
// LEITURA DOS TSOPS
// =====================================================

int lerDirecaoTSOP() {

  int mudancas[NUM_TSOPS] = {0};

  int ultimo[NUM_TSOPS];

  for (int i = 0; i < NUM_TSOPS; i++) {

    ultimo[i] =
      digitalRead(
        pinosTSOP[i]
      );
  }

  unsigned long inicio =
    millis();

  while (
    millis() - inicio <
    TSOP_TEMPO_JANELA
  ) {

    for (
      int i = 0;
      i < NUM_TSOPS;
      i++
    ) {

      int atual =
        digitalRead(
          pinosTSOP[i]
        );

      if (
        atual != ultimo[i]
      ) {

        mudancas[i]++;

        ultimo[i] =
          atual;
      }
    }
  }

  int max_mudancas = 0;

  int melhor_direcao = -1;

  for (
    int i = 0;
    i < NUM_TSOPS;
    i++
  ) {

    if (
      mudancas[i] >=
      TSOP_LIMIAR_MUDANCAS
    ) {

      if (
        mudancas[i] >
        max_mudancas
      ) {

        max_mudancas =
          mudancas[i];

        melhor_direcao =
          i;
      }
    }
  }

  return melhor_direcao;
}

// =====================================================
// MOVIMENTAÇÃO BASEADA NO TSOP + IR SEEKER
// =====================================================

void movimentarPorTSOP() {

  int direcao =
    lerDirecaoTSOP();

  Serial.print(
    "TSOP detectado: "
  );

  Serial.print(
    direcao
  );

  // ===================================================
  // TSOP 0 = MEIO
  // ===================================================

  if (direcao == 0) {

    Serial.print(
      " | MEIO"
    );

    Serial.print(
      " | Intensidade: "
    );

    Serial.println(
      ballIntens
    );

    // -----------------------------------------------
    // MEIO + INTENSIDADE MENOR QUE 150
    // -----------------------------------------------

    if (ballIntens < 150) {

      Serial.println(
        ">>> TSOP 0 + INTENSIDADE < 150: FRENTE"
      );

      moverFrente();

    }

    // -----------------------------------------------
    // MEIO + INTENSIDADE 150 OU MAIOR
    // -----------------------------------------------

    else {

      Serial.println(
        ">>> TSOP 0 + INTENSIDADE >= 150: PARAR"
      );

      parar();
    }

    return;
  }

  // ===================================================
  // DEMAIS TSOPS
  // ===================================================

  Serial.println();

  switch (direcao) {

    // Nenhum sensor detectou
    case -1:

      parar();

      break;

    // TSOP 1: esquerda
    case 1:

      moverEsquerda();

      break;

    // TSOPs 2 e 3:
    // diagonal trás + esquerda
    case 2:
    case 3:

      moverDiagonalTrasEsquerda();

      break;

    // TSOPs 4 e 5:
    // trás
    case 4:
    case 5:

      moverTras();

      break;

    // TSOPs 6, 7 e 8:
    // diagonal trás + direita
    case 6:
    case 7:
    case 8:

      moverDiagonalTrasDireita();

      break;

    // TSOPs 9, 10 e 11:
    // diagonal trás + esquerda
    case 9:
    case 10:
    case 11:

      moverDiagonalTrasEsquerda();

      break;

    // TSOPs 12 e 13:
    // diagonal trás + direita
    case 12:
    case 13:

      moverDiagonalTrasDireita();

      break;

    // TSOPs 14 e 15:
    // direita
    case 14:
    case 15:

      moverDireita();

      break;

    default:

      parar();

      break;
  }
}

// =====================================================
// BOTÃO - ZERAR ORIENTAÇÃO
// =====================================================

void verificarBotaoZero() {

  bool botaoAtual =
    digitalRead(
      botao
    );

  if (
    botaoAnterior == HIGH &&
    botaoAtual == LOW &&
    setado == false
  ) {

    setado = true;

    zerarOrientacao();

    Serial.println(
      ">>> ORIENTACAO ZERADA <<<"
    );
  }

  if (
    botaoAtual == HIGH
  ) {

    setado = false;
  }

  botaoAnterior =
    botaoAtual;
}

// =====================================================
// SETUP
// =====================================================

void setup() {

  Serial.begin(115200);

  Wire.begin();

  // ===================================================
  // MOTORES
  // ===================================================

  int inPins[] = {

    M1_IN1,
    M1_IN2,

    M2_IN1,
    M2_IN2,

    M3_IN1,
    M3_IN2,

    M4_IN1,
    M4_IN2
  };

  for (
    int i = 0;
    i < 8;
    i++
  ) {

    pinMode(
      inPins[i],
      OUTPUT
    );

    digitalWrite(
      inPins[i],
      LOW
    );
  }

  int pwmPins[] = {

    M1_PWM,
    M2_PWM,
    M3_PWM,
    M4_PWM
  };

  for (
    int i = 0;
    i < 4;
    i++
  ) {

    pinMode(
      pwmPins[i],
      OUTPUT
    );

    analogWrite(
      pwmPins[i],
      0
    );
  }

  // ===================================================
  // TSOPS
  // ===================================================

  for (
    int i = 0;
    i < NUM_TSOPS;
    i++
  ) {

    pinMode(
      pinosTSOP[i],
      INPUT
    );
  }

  // ===================================================
  // BOTÃO
  // ===================================================

  pinMode(
    botao,
    INPUT_PULLUP
  );

  // ===================================================
  // PARAR MOTORES
  // ===================================================

  parar();

  // ===================================================
  // BNO055
  // ===================================================

  if (!bno.begin()) {

    Serial.println(
      "ERRO: BNO055 nao encontrado!"
    );

    while (1);
  }

  delay(1000);

  bno.setMode(
    OPERATION_MODE_NDOF
  );

  if (calibrar) {

    bno_calibrar();
  }

  zerarOrientacao();

  // ===================================================
  // MENSAGENS INICIAIS
  // ===================================================

  Serial.println(
    ">>> SISTEMA INICIADO <<<"
  );

  Serial.println(
    ">>> IR SEEKER ATIVO <<<"
  );

  Serial.println(
    ">>> TSOPS ATIVOS <<<"
  );
}

// =====================================================
// LOOP
// =====================================================

void loop() {

  // ===================================================
  // VERIFICA BOTÃO
  // ===================================================

  verificarBotaoZero();

  // ===================================================
  // LÊ IR SEEKER
  // ===================================================

  lerSeeker();

  // ===================================================
  // BOTÃO SOLTO = PARA
  // ===================================================

  if (
    digitalRead(botao) == HIGH
  ) {

    parar();

  }

  // ===================================================
  // BOTÃO PRESSIONADO = ATIVA ROBÔ
  // ===================================================

  else {

    movimentarPorTSOP();
  }

  delay(10);
}