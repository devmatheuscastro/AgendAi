# AgendAí

MVP web local, com lógica, rotas, sessões e renderização em **Python**. Usa apenas a biblioteca padrão (Python 3.10 ou superior); não é necessário instalar pacotes.

## Executar

```powershell
python app.py
```

Abra http://127.0.0.1:8765. Para encerrar, pressione Ctrl+C no terminal. No Windows, você também pode dar dois cliques em `iniciar.bat` e manter a janela aberta.

Se a porta estiver ocupada, use `python app.py --port 8766` e abra http://127.0.0.1:8766.

## Experimentar

- Entre com qualquer nome, e-mail e senha e escolha um dos quatro perfis. O cadastro também abre a plataforma sem autenticação real.
- Paciente: alterne a busca por especialidade/nome, escolha uma data e um horário, informe o motivo obrigatório e confirme. Consulte e cancele agendamentos e veja os avisos.
- Profissional: representa Marina Costa nesta demonstração. Veja sua agenda, cancele consultas e configure disponibilidade. Bloqueie todos os horários de um dia para ver o estado “Indisponível” ao agendar.
- Atendente: provisoriamente pode pesquisar, agendar em nome de um paciente e consultar/cancelar os agendamentos. Essa divisão de responsabilidades ainda precisa ser validada.
- Admin: pode desligar funcionários. Profissionais desligados saem da busca; os agendamentos existentes são preservados. O desligamento é apenas uma alteração nos dados demonstrativos.
- Para testar avisos: agende como paciente com Marina; saia, entre como profissional e cancele; volte ao paciente usando o mesmo e-mail e abra Avisos.

## Limites do protótipo

Todos os dados são fictícios e mantidos em memória, compartilhados entre as sessões locais. Reiniciar o servidor restaura a demonstração. Não há banco de dados, envio de e-mail, lembretes automáticos, autenticação ou autorização de produção. O seletor de perfil existe apenas para navegar pelo protótipo. Não utilize dados reais de pacientes.

Horários são blocos fixos, de segunda a domingo, e valores/localidades são ilustrativos. A fonte Google Fonts é opcional; sem internet, a interface usa fontes locais. O servidor aceita conexões somente deste computador.

