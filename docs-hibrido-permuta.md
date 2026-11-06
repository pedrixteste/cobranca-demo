# Híbrido com escolha de formas + permuta (06/11/2026)

Pedido: no pagamento híbrido, escolher QUAIS formas foram usadas (Pix, cartão de crédito,
permuta) e poder juntar permuta. Caso real: cliente que paga parte no Pix e parte em permuta.
Este texto serve para levar a mesma mudança ao app das franquias.

## O que a pessoa vê
- Nova cobrança → Cobrança híbrida → bloco 1 "Formas de pagamento": três pílulas
  (Pix | Cartão de crédito | Permuta). Vem marcado Pix + Cartão (igual a antes).
  Menos de duas marcadas = aviso e não salva.
- Só aparecem os blocos das formas marcadas: "Parte no Pix" (entrada + parcelas),
  "Parte no cartão" (passadas), "Parte na permuta" (os mesmos campos da tela Permuta:
  valores com data + "Adicionar outro valor"; retiradas opcionais; saldo ao vivo).
- "Valores": valor total + "Quanto vai no Pix / no cartão / na permuta". Uma pode ficar em
  branco (fica com o resto). O valor da permuta já vem preenchido no bloco dela.
- Resumo mostra cada parte; a conferência soma tudo (Pix + cartão + valores da permuta = total)
  com as caixas de sempre ("Faltam R$ X" / "Passa R$ X do total" / "Fecha certinho").
- Ficha: "No Pix", "No cartão", "Na permuta" (cartão Total/Retirado/Saldo, "Valores da
  permuta" e "Retiradas" com Alterar, "Adicionar valor", "Adicionar retirada").
  O "Total" do topo é o combinado de tudo; Pago/Falta/Atrasado são só dinheiro.
- Relatório: etiqueta "Híbrido" com uma faixa por forma (Pix azul, cartão rosa, permuta
  verde-água); no cartão, "falta R$ X · saldo R$ Y" (o saldo em verde-água).

## Decisões
1. Sem coluna nova. A parte da permuta grava as mesmas linhas de uma permuta em `_Parcelas`
   (Forma "Crédito de permuta" para cada valor; "Permuta" + Produto para cada retirada; Status
   Paga), dentro da mesma cobrança (`Tipo` "Híbrido"), numeradas depois das de dinheiro.
2. "Híbrido" continua CALCULADO pelas formas presentes: mais de uma = híbrida
   (Pix+cartão, Pix+permuta, cartão+permuta, as três). `c["formas"]` diz quais.
3. `c["permuta"]` = a cobrança INTEIRA é permuta (como antes). Novo `c["com_permuta"]` =
   permuta inteira OU híbrida com parte na permuta. `saldo`, `total_permuta`, `retirado`,
   `creditos`, `retiradas` valem para as duas. `por_forma["Permuta"]` = retirado/saldo.
4. Dinheiro x permuta: `pago`, `falta`, `atrasado`, situação, próxima, "vai até" = só
   Pix/cartão. Híbrida fica Quitada quando o dinheiro foi pago, mesmo com saldo de permuta.
5. Relatório: Recebido / A receber / Atrasado só com dinheiro; "Saldo para retirar" soma a
   permuta inteira E a parte das híbridas. Agenda e Telegram: linha de permuta já entra paga,
   então nunca aparece.
6. Filtro Forma: "Permuta" acha as permutas E as híbridas com permuta; "Híbrido" acha todas
   as híbridas; Pix e Cartão continuam só as de uma forma. Busca acha pelo produto e por "permuta".
7. "Valor Total": na permuta inteira continua sendo regravado com a soma dos valores. Na
   híbrida é o combinado e NÃO muda sozinho ao mexer na permuta (igual ao alterar parcela): a
   ficha mostra "O total combinado é X, mas as partes somam Y" e acerta em Editar dados.
8. Janela Recebi ("Pagamento híbrido") e "Forma de pagamento" em Alterar/Adicionar continuam
   só Pix/cartão. Única mudança: em cartão + permuta, Adicionar já vem no cartão.
9. Backup/Excel/restauração: nada muda (mesma planilha; as linhas de permuta aparecem com a
   forma delas na aba "Parcela por parcela").

## Onde mexeu
- `nucleo.py`: `FORMAS_HIBRIDO`, `LINHAS_PERMUTA`, `parcelas_hibrido(..., creditos, retiradas,
  quem)`, `montar_cobrancas` (dinheiro x parte na permuta), `casa_forma`/`filtrar`,
  `casa_busca`, `resumo`.
- `app.py`: `tela_hibrido` (pílulas `hb_formas`, blocos por forma, `sec_hb_pm`),
  `_bloco_valores_permuta(a_dividir=)`, `_chip_cobranca`, `_nome_tipo`, `_html_cliente`,
  `tela_cobranca` ("Na permuta"), `_html_numeros_permuta` + `_listas_permuta` (usados também
  pela ficha da permuta), `_dlg_valor_permuta` (não regrava o total na híbrida),
  `_dlg_adicionar`, excluídas.
- `estilo.css`: `.tp-hib.hb-px-pm / .hb-ct-pm / .hb-tres`, `.cc-sp`, bordas `hb_pm_`.
- `demo.py`: FLORICULTURA JARDIM (EXEMPLO), Pix + permuta.
- Testes: `tests/test_hibrido_permuta.py` (19), `ferramentas/teste_hibrido_permuta.py`;
  `teste_hibrido.py` e `teste_permuta.py` ajustados ao exemplo novo (contagens).
