# Produção audiovisual

Método geral para vídeos comerciais com cenas, voz e motion graphics editável em Premiere e After Effects. As escolhas de marca, roteiro, estilo e provedores pertencem a cada demanda.

**Fonte única do processo:** [PLANEJAMENTO_AUTOMACAO.md](PLANEJAMENTO_AUTOMACAO.md). O documento inclui ordem das etapas, direção de cenas e motion, aprovações, fichas, continuidade entre agentes e a distinção entre execução manual, código disponível e automação futura.

## Conteúdo

- `PLANEJAMENTO_AUTOMACAO.md`: planejamento detalhado e modelos de preenchimento.
- `kit/av.py`: continuidade local, notas editoriais persistentes (`note`), retornos recentes, operações pendentes, hooks Claude Code e grids de revisão.
- `kit/test_av.py`: testes de continuidade e cobertura temporal dos grids.
- `kit/requirements.txt`: dependência do comando de grid; FFmpeg/FFprobe também precisam estar disponíveis.
- `AGENTS.md` e `CLAUDE.md`: entradas curtas para agentes; não duplicam o planejamento.

## Uso

Clonar/baixar este repositório para trabalhar localmente. Preencher o briefing da seção2 para a nova demanda e manter decisões/estado do cliente na pasta dela. Inicializar o kit nessa pasta conforme seção11; não copiar o registro `.continuidade` de outro cliente. Ler apenas a etapa necessária, em vez de carregar todos os documentos e logs.

O kit não gera mídia por IA nem edita Adobe. As pontes e contas precisam ser configuradas/testadas por projeto. Não há dependência de assinatura Higgsfield ou créditos generativos extras Adobe.

A seção3 orienta descobrir referências mesmo em pastas diferentes; a seção5 define lógica das cenas, consistência, linguagem de motion e grid para aprovação; a seção11 orienta registro durante o trabalho e troca de agente; a seção12.4 reúne a pesquisa comparativa de pontes e pipelines. Um grid gerado para planejar o design é diferente de um grid de capturas para revisar um render.

Teste local:

```text
python -m unittest discover -s kit -p test_av.py
```

Este repositório não recebe mídias de clientes, projetos Adobe, credenciais, sessões de navegador, logs privados ou registros locais de continuidade.
