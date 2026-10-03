# Baseline Arduino GIGA

`giga_baseline.ino` contém exatamente o trecho C++ fornecido pelo usuário no
pedido inicial de 03/10/2026, extraído do anexo `Pasted text.txt`.
O conteúdo após a abertura do bloco C++ até o fim do anexo foi preservado,
incluindo formatação e quebras de linha. O anexo não continha fechamento do bloco.

Comparação textual com o trecho original: idêntico. SHA-256 do arquivo preservado:

```text
70fae2b690a0a7be5cc43dd1b7fb4a5fbfa22c7e4ac2ad20e71c7747c43b2513
```

Para conferir no PowerShell:

```powershell
Get-FileHash firmware/giga_baseline/giga_baseline.ino -Algorithm SHA256
```

Não foi compilado nem enviado ao GIGA nesta etapa. Versões do core da placa e das
bibliotecas precisam ser identificadas no FabLab antes de reproduzir o build.
As dependências presentes no sketch incluem Wire, Adafruit Sensor, Adafruit BNO055
e HTInfraredSeeker.

## Comportamento observado por leitura

- Motores inicializados parados; falha de inicialização do BNO055 bloqueia o setup.
- O botão pressionado habilita a movimentação; solto solicita parada no próximo
  ciclo. A borda de pressão também zera a orientação.
- O IR Seeker é lido a cada ciclo. Intensidade e direção são registradas; a decisão
  de movimento usa direção TSOP e intensidade IR no caso TSOP 0.
- TSOPs são amostrados por 50 ms; vence o primeiro índice com maior contagem válida.
- TSOP 0 avança com intensidade menor que 150 e para com intensidade maior ou igual.
- Sem direção TSOP válida, os motores param. Os demais índices usam o mapeamento
  de movimentos definido no sketch.
- `calcularRotacaoBNO()` existe, mas não é chamada pelo loop. `calibrar` é falso.
- A compensação do motor 4, os pinos e os limites de velocidade foram preservados.
- Não existe recepção de dados do sistema de visão.

Estes pontos descrevem o código, não testes físicos. Antes de integrar visão,
registrar as versões reais, medir o tempo do loop e definir explicitamente quais
comportamentos poderão mudar. O M1 não altera este firmware.
