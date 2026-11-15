# Início do relatório

Todos os testes a partir de agora serão feitos com um dataset mais completo, que utiliza todos os 11 sites que passam nas regras, e todos os edifícios de cada site, contra 6 sites e 20 edifícios por site.

Inicialmente, irei comparar arquiteturas recorrentes contra o MLP original.

> Observação:
> No experimento da Semana 9, o MLP testado utilizava apenas os lags t-1, t-24 e t-168, as outras das features em t-1 e o seno e cosseno da hora e semana atuais,
> em um teste inicial com os modelos recorrentes, todos eles foram superiores à MLP original.
> Porém os modelos recorrentes todos recebiam como entrada as últimas 24 horas, a CNN-LSTM como uma matriz 2d com dimensão features X horas
> e as RNNs com uma sequência de 24 vetores de tamanho 17.
> Nesse sentido, fiz também uma variação dele, para que na comparação recebesse os mesmos dados que os modelos recorrentes, a entrada
> passou a ser, uma janela completa de 24 horas, ou seja, a hora t passa a ter `17 * 24 = 408` features, com as 24 horas achatadas, passando de
> 17 features para 408 features na camada de entrada, o experimento a seguir foi feito comparando também o MLP original com menos features.
 

