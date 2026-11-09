# Golden set: 69 questions, gemini-3.5-flash-lite

| System | Fact right | Fact, number | Fact, direct | Fact, colloquial | Fact, multi-hop | Cites a labeled question | Citations dropped | Refuses out of scope | Refuses in scope | Model calls | Tool calls | Tokens | Median latency |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| rag-pages | 90% | 88% | 100% | 90% | 83% | 91% | 0 | 100% | 3% | 1.00 | 0.00 | 2,643 | 1.0 s |
| rag-questions | 98% | 100% | 100% | 100% | 92% | 97% | 0 | 100% | 0% | 1.00 | 0.00 | 1,823 | 1.0 s |
| agent | 97% | 100% | 100% | 95% | 92% | 95% | 0 | 100% | 0% | 1.01 | 0.01 | 2,179 | 1.1 s |

Means per question, except latency. A fact is right when the answer contains it, ignoring case and spaces.

## Every wrong answer

### rag-pages: 6

- **n08** (no "28.467,20") Qual é a faixa de isenção da tabela progressiva anual do ano-calendário de 2025?  
  Expected [61], found False, cited []  
  > Não encontrei isso no Perguntas e Rpostas do IRPF 2026.
- **n14** (refused) Qual é a data de pagamento do primeiro lote de restituição de 2026?  
  Expected [76], found True, cited []  
  > Não encontrei isso no Perguntas e Respostas do IRPF 2026.
- **c14** (refused) A restituição que caiu na minha conta ano passado conta como renda?  
  Expected [297], found False, cited []  
  > Não encontrei isso no Perguntas e Respostas do IRPF 2026.
- **c18** (no "chave CPF") Dá pra receber a restituição pelo PIX?  
  Expected [70], found False, cited [74, 122, 75]  
  > Sim, é possível receber a restituição informando a chave PIX do titular da declaração [074] [122]. Essa opção também serve como critério de prioridade no recebimento [075].
- **m02** (no "conta pagamento") Posso receber minha restituição na conta do meu marido? Se não, em que tipo de conta pode ser?  
  Expected [72, 70], found True, cited [72]  
  > Não. A restituição só é creditada em conta se o declarante for seu titular ou utilizar conta conjunta [072].
- **m05** (no "Não é devida a multa") Qual é a multa por entregar a declaração atrasada, e ela vale para quem nem era obrigado a declarar?  
  Expected [24, 25], found True, cited [24]  
  > O contribuinte obrigado a apresentar a declaração, no caso de apresentação após o prazo ou da não apresentação, fica sujeito a uma multa calculada da seguinte forma: existindo imposto devido, a multa é de 1% ao mês-calendário ou fração de atraso sobre o imposto devido, com valor mínimo de R$ 165,74 

### rag-questions: 1

- **m11** (no "3.561,50") Aula de natação do meu filho entra como instrução? E qual é o limite da dedução com educação?  
  Expected [415, 400, 401], found True, cited [415]  
  > Os pagamentos de aulas de natação não são dedutíveis por falta de previsão legal [415].   O manual não trata do limite da dedução com educação.

### agent: 2

- **c02** (no "24 anos") Meu filho tem 23 anos e faz faculdade. Ainda dá pra colocar ele como dependente?  
  Expected [350, 340], found True, cited [340, 350]  
  > Sim, o filho de 23 anos que está cursando estabelecimento de ensino superior pode ser considerado dependente [340] [350].
- **m09** (no "mais 1%") Vou pagar o imposto em quotas. Como é calculado o valor da segunda quota?  
  Expected [63, 64], found True, cited [64]  
  > O valor da segunda quota (com vencimento em 30/06/2026) corresponde ao valor apurado acrescido de 1% [064].
