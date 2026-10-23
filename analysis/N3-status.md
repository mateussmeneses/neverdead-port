# N3 - HLE e primeiro boot rastreavel

Data: 2026-10-21. Estado: **boot traceado por 60 segundos alcancou a
inicializacao das threads Asura e o carregamento de recursos; nao houve trap
PPC, FATAL ou import marcado como nao implementado nesse intervalo. A consulta
XCTD de `NtQueryInformationFile` foi implementada e testada. Isso nao comprova
estabilidade prolongada, video ou jogabilidade.**

## Fatos verificados

- O build integral do host foi concluido pelo CMake/Ninja em
  `build\n2-neverdead`. A configuracao CMake reexecutou o codegen depois de
  cada alteracao de limites de funcao, e os shards afetados foram recompilados
  e relinkados.
- O runtime carregou `default.xex`, mapeou o codigo convidado em
  `0x821A0000-0x827C05E4`, registrou 24.664 funcoes recompiladas, resolveu
  95 imports XAM e 174 imports `xboxkrnl`. Estes totais confirmam setup e
  resolucao inicial, nao a semantica correta de todos os imports.
- O boot entrou pelo entry point observado em N1, `0x826D1288`. Em
  `logs\n3-run05.log`, o runtime iniciou o `MainThread`, executou a funcao de
  thread `0x826DD520` e chamou `SetThreadName` para
  `Asura_Task_System_0`, `Asura_Task_System_1`, `Asura_Task_System_2` e
  `Asura_AsyncLoader Thread`. Isso comprova que a inicializacao do sistema de
  tarefas Asura foi alcancada; nao comprova jogo jogavel.
- Em `logs\n3-run10.log`, um boot traceado e limitado a 60 segundos iniciou
  `Asura_Task_System_0..2`, `Asura_AsyncLoader Thread` e
  `TextureStreamingThread`, e chegou ao carregamento de recursos Asura. O
  wrapper encerrou o processo ao final do limite; o log termina durante uma
  linha, portanto a execucao nao foi um encerramento limpo.
- A mesma janela registrou 139 resultados da classe XCTD de
  `NtQueryInformationFile`: 132 com `xctd=0` e 7 com `xctd=1`. Nao houve
  `[FATAL]` ou ocorrencia de `unimplemented` no log. Esses resultados sao
  evidencias da janela observada, nao uma garantia para todas as fases do jogo.
- `XamNotifyCreateListener(mask=0xEF, is_system=0, max_version=9)` retornou o
  handle `0xF800009C`. Nessa execucao inicial, nenhum import ausente precedeu
  os traps PPC; um trace posterior identificou a consulta XCTD nao implementada.
- A renderizacao nao foi exercitada: o runtime informou
  `Runtime initialized without graphics system (native rendering mode)`.
- Para corrigir enderecos indiretos efetivamente observados, foram adicionadas
  a `src\neverdead_config.toml` as funcoes:
  - `0x824DDEC8`, tamanho `0x10`: leaf PPC de quatro instrucoes; termina em
    `blr` em `0x824DDED4`, antes da proxima entrada `.pdata` em `0x824DDED8`.
  - `0x824DDF90`, tamanho `0x10`: leaf PPC de quatro instrucoes. O trap
    registrou `LR=0x822CB24C`; o caller em `0x822CB1E0` executa `bctrl` em
    `0x822CB248`. A proxima entrada `.pdata` e `0x824DDFA0`.
  - `0x82736FE0`, tamanho `0xF8`: destino de `bctrl` em `0x82736D74`,
    identificado por `LR=0x82736D78`; o corpo termina em tail `bctr` em
    `0x827370D0`, antes da proxima entrada `.pdata` em `0x827370D8`.
  - `0x8225C120` (0x8), `0x827383D0` (0x100) e `0x827484A0` (0x18):
    limites adicionais registrados apos os traps observados e aceitos pelo
    codegen.
  O codegen validou e emitiu os fontes correspondentes; essas funcoes nao sao
  stubs de sucesso.
- As escritas repetidas `XMA: Write to unknown register (0601)` persistem:
  22.430 ocorrencias no `n3-run10.log`. Sao mensagens de debug do caminho de
  audio; nao produziram FATAL na janela, mas sua semantica e efeito no audio
  continuam desconhecidos.
- `refs\core\rexglue-sdk\src\system\function_dispatcher.cpp` foi alterado
  apenas para que `InvalidFunctionTrap` registre o alvo PPC, LR e SP. O logger
  ja prefixa timestamp e thread. Isso permitiu localizar os callsites; nao e
  ainda um tracer uniforme de imports/NIDs nem uma stack completa.

## Estado do bloqueio

Os alvos PPC `0x8225C120` e `0x827383D0`, que anteriormente causavam traps,
foram adicionados a configuracao com limites aceitos pelo codegen. O run10 nao
reproduziu traps PPC nem identificou outro import nao implementado durante os
60 segundos observados. A execucao foi encerrada pelo limite do teste, nao por
um bloqueio reproduzido. O proximo bloqueio funcional permanece indeterminado;
as escritas XMA desconhecidas sao o aviso tecnico mais frequente, nao um erro
fatal confirmado.

## HLE, logging e testes

`NtQueryInformationFile` (NID `0x00E8`) foi implementado para a classe de
informacao XCTD (27). A consulta verifica o magic big-endian `0x0FF512ED` sem
alterar a posicao atual do arquivo; falhas de leitura nao sao convertidas em
sucesso. O log inclui NID, PC convidado, SP, uma stack simplificada de um frame,
path, classe, status, bytes de informacao e resultado XCTD. O teste
`file_info_test.cpp` cobre magic, arquivo normal e cabecalho curto.

Foi adicionado `sync_primitives_test.cpp` para eventos manual/auto-reset,
mutant e timer de disparo unico. A suite ja contem cobertura de tabela de
handles (`kernel\object_table_test.cpp`), tempo (`core\chrono_test.cpp`),
alocacao (`memory\heap_allocation_test.cpp`) e paths convidados
(`system\guest_path_test.cpp`). Esses testes cobrem primitivas e componentes do
SDK; nao equivalem a testes completos dos contratos de cada import HLE. O
build `unit_tests` passou e os cinco testes focados (eventos, mutant, timer e
XCTD) passaram. Na suite completa, 2 dos 219 casos nao passaram: o teste nao
relacionado `Depfile escapes characters make treats as syntax` falhou, e
`ppc_tests_NOT_BUILT` nao foi executado porque esse target nao existe. Quatro
casos BitStream foram marcados skipped. Excluindo essas duas excecoes,
`ctest` aprovou os 217 testes restantes. Resultado detalhado:
`logs\n3-sdk-unit-full-final.log`.

A instrumentacao de `InvalidFunctionTrap` registra alvo, LR e SP, com
timestamp/thread do logger. O logging detalhado de NID/callsite/resultado
continua especifico a `NtQueryInformationFile`, nao uniforme para todos os
imports. A stack registrada e de um frame, nao unwind completo.

## Comandos reproduziveis e evidencias

Build:

```powershell
cmake --build C:\projetos\neverdead\build\n2-neverdead --config Release --parallel 12
```

Execucao (o dump original foi apenas lido):

```powershell
C:\projetos\neverdead\build\n2-neverdead\neverdead.exe `
  --game_data_root=C:\projetos\NeverDeadxex `
  --user_data_root=C:\projetos\neverdead\build\n2-neverdead\n3-user-data-run10 `
  --cache_root=C:\projetos\neverdead\build\n2-neverdead\n3-cache-run10 `
  --log_file=C:\projetos\neverdead\logs\n3-run10.log `
  --log_level=trace --log_noisy
```

Logs principais: `logs\n3-full-build-target01.log` a
`logs\n3-full-build-target04.log`, `logs\n3-sdk-unit-build-retry02.log`,
`logs\n3-sdk-unit-test.log`, `logs\n3-sdk-unit-full-final.log` e
`logs\n3-run01.log` a `logs\n3-run10.log`.
Para o build de testes, os 15 arquivos-placeholder de libmspack foram
temporariamente materializados como hardlinks e restaurados byte a byte
(`RESTORE_VERIFIED=True`); sem isso, o build tenta compilar o texto relativo
dos placeholders como C/C++. O run10 foi encerrado pelo wrapper apos 60
segundos (PID 37004); seu exit code forcado nao e resultado de erro interno do
runtime.

## Marco e limites

| Marco | Resultado |
|---|---|
| Build integral do host | Concluido |
| Carregar XEX, resolver imports e entrar no codigo do titulo | Concluido |
| Alcancar inicializacao Asura e carregar recursos | Observado no run10 limitado a 60 s |
| Boot sem traps PPC/import nao implementado | Sem ocorrencias no run10; estabilidade prolongada ainda nao provada |
| HLE XCTD identificada por trace | Implementada e validada por teste e run10 |
| Testes de handles/eventos/mutant/timer/tempo/alocacao/paths | Cobertura existente e focada aprovada; suite completa ainda tem falha nao relacionada e PPC tests ausente |
| Video/renderizacao Xenos | Nao exercitado |

Proximo gate: completar a instrumentacao estruturada dos imports boot-relevantes
com nome/NID e callsite convidado, sem inferir chamadas nao observadas; depois
prolongar a observacao com encerramento controlado, investigar o registro XMA
`0x0601` e habilitar/validar uma fase de renderizacao. Ainda nao se afirma boot
estavel, video funcional ou jogabilidade.
