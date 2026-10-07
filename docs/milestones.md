# Milestones

Avançar somente após implementar, testar, executar e registrar o resultado da
etapa atual. Não interpretar simulação como validação do hardware.

| Etapa | Objetivo | Critério de validação |
| --- | --- | --- |
| M1 | Pipeline finito sem hardware, baseline visual e registros | Testes automatizados, execução local de 60 frames e sketch preservado |
| M2 | Ruído, oclusão, falha de câmera e atraso controlados | Cenários reproduzíveis e métricas corretas em condições adversas |
| M3 | Leitura de gravações e baseline para a bola real | Dataset anotado, avaliação de falsos positivos/negativos e localização |
| M4 | Raspberry Pi com uma webcam | FPS, latência, temperatura e recuperação medidos no dispositivo |
| M5 | Expansão progressiva de câmeras | Duas webcams na Pi, segunda Pi e depois quatro webcams, com medições a cada passo |
| M6 | Comunicação e integração | Pis entre si, GIGA em observação, robô e ambiente real; falhas e expiração testadas |

## Escopo encerrado no M1

A fonte sintética gera um alvo simples com resposta conhecida. O detector processa
os pixels; o avaliador compara o resultado com essa resposta. Registros e testes
cobrem bola presente e ausente, centro conhecido, candidatos inadequados,
falhas de aquisição, descarte de recursos e proteção de resultados existentes.

A desconexão do M1 foi exercitada por uma fonte de teste. O M2 adicionou injeção
configurável de perturbações e uma comparação reproduzível na CLI.
Tracking/fusão não entram sem uma necessidade demonstrada e referenciais definidos.

## M2 implementado e executado

Ruído com semente, oclusão parcial/total, perda terminal da fonte e atraso virtual
foram implementados. O pipeline rejeita frames acima de uma idade configurável.
O comparador registra resultados completos, parciais e descartes separadamente.

A validação local de 03/10/2026 executou 37 testes e sete cenários de até 60 frames.
O ruído revelou 24 falsos negativos; oclusão parcial deslocou o centro em média
5,39 pixels; dados com 200 ms de idade foram rejeitados pelo limite de 100 ms.
Consulte [os resultados e limitações](validation-m2.md).

## M3 implementado e executado em 05/10/2026

Três gravações reais (1535 frames) foram processadas com setores Left/Front/Right,
círculo acompanhando medidas atuais e reprodução opcional sincronizada com o vídeo.
O dataset inicial tem 79 anotações aproximadas feitas por inspeção visual.
O perfil de 320 pixels encontrou 48 das 50 bolas anotadas, com duas perdas sob a
mão e nenhum falso positivo nas amostras; 62 testes passaram.

São resultados exploratórios em gravações usadas no ajuste. O M3 ainda precisa
de revisão humana das anotações e vídeos independentes em outras iluminações e
distâncias. O próximo trabalho de hardware é M4, com uma webcam na Pi4B;
FPS, atraso, temperatura e recuperação ainda precisam ser medidos na placa.
Consulte [a validação, comandos e demonstração](validation-m3.md).

## O que pode ser feito em casa

Em 07/10, Bruno relatou primeiro ensaio de câmera e pan/tilt na Pi4B com arquivo
standalone. Código recuperado/integrado, entrega `.pyz` e 81 testes locais;
sentidos físicos e métricas da Pi seguem pendentes. M4 ainda não concluído.
Consulte [validation-m4.md](validation-m4.md).

Contratos, testes, simulação, leitura de vídeos fornecidos pela equipe, avaliação
e análise dos registros. Vídeos reais do FabLab poderão ser avaliados sem conexão
com o hardware durante o desenvolvimento.

## O que depende do FabLab

1. Confirmar modelos das placas/webcams, versões e disponibilidade de Python.
2. Gravar a bola real em diferentes iluminações e distâncias; verificar filtros
   infravermelhos, exposição e se a bola é distinguível dos demais objetos.
3. Validar Raspberry Pi + uma webcam e depois + duas webcams.
4. Adicionar a segunda Raspberry Pi e depois operar as quatro webcams.
5. Medir e validar comunicação entre as Raspberry Pis.
6. Definir o protocolo e validar recepção no GIGA sem comandar motores pela visão.
7. Integrar no robô com política explícita para dados perdidos, inválidos e antigos.
8. Testar no ambiente real e comparar com o baseline dos sensores atuais.

O firmware existente tem uma janela bloqueante de leitura TSOP de 50 ms, além
das leituras e do delay de 10 ms. A integração deverá medir esse tempo e preservar
o comportamento acordado. O mapeamento dos motores, compensação M4 e regra do
botão não foram modificados no M1.
