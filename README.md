# residencia-experimentos

Experimentos práticos da residência: fusão de sensores em hardware real (ESP32 + IMU + sensores de distância), comparando Edge AI e fusão tardia.

![Kit de sensores](fritzing/Residência%20-%20Kit%20Sensores%20V1_bb.png)

## Pastas

- **`esp/`** — firmware do ESP32, em PlatformIO.
- **`fritzing/`** — diagramas de fiação do kit de sensores (`.fzz`, com o esboço de código `.ino` e a imagem de montagem acima).
- **`viz/`** — ferramenta simples de visualização das leituras dos sensores em tempo real.
- **`_archive/`** — versões anteriores/descartadas de ferramentas, fora do controle de versão.

## Experimento: fusão de dados (Kalman) vs. processamento de borda (evento) no consumo de energia

Testes práticos num nó ESP32 com IMU (MPU6050) e medição de corrente/potência via INA219,
comparando diferentes formas de processar e transmitir os dados antes de decidir sobre
otimização energética.

### Teste inicial: dado bruto vs. fusão por filtro de Kalman

Comparação entre transmitir o dado bruto do IMU via rede (UDP) a cada leitura, e transmitir o
resultado de um filtro de Kalman aplicado a esse mesmo dado (fusão acelerômetro+giroscópio em
ângulo de pitch/roll) antes de enviar.

![Energia: dado bruto vs. filtro de Kalman](esp/out/energia.png)

É claro que não vai haver diferença nenhuma na energia — estamos transmitindo dados direto do
mesmo jeito (periodicamente, a 100 Hz), só mudando o tamanho do payload. Devemos pensar em como
o processamento na borda pode otimizar a energia, não só o tamanho do dado enviado.

### Teste seguinte: processamento de borda com detecção de evento

O teste seguinte foi feito simulando um evento simples de queda, com uma detecção baseada na
aceleração do sensor — um pacote é enviado apenas quando uma queda é detectada, em vez de
transmitir continuamente.

![Energia: dado bruto vs. evento de queda](esp/out/energia_fall.png)

### Comparação de potência média

![Potência média por modo, com desvio padrão](esp/out/potencia_media.png)

A potência média no caso sem processamento pelo filtro de Kalman foi de 714.8 mW (± 21.4), e com
o filtro foi 714.3 mW (± 16.9), ou seja, estatisticamente iguais. Com o evento de queda simulado,
foi de 364.1 mW (± 95.9).
