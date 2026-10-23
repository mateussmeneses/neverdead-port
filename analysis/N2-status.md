# N2 - Primeiro codegen e compilacao de shard

Data: 2026-10-21. Estado: **codegen completo; um shard PPC recompilado para
objeto C++ compilado**. O executavel integral e o runtime ainda nao foram
construidos.

## Fatos verificados

- XEX analisado em N1: imagem base `0x82000000`, entry point `0x826D1288`,
  15 secoes e 269 imports. O ReXGlue carregou `default.xex` e reportou Title ID
  `0x4B4E081F`, Media ID `0x5D5CA48B` e versao `0.0.0.9`.
- O SDK ReXGlue 0.10.0 foi configurado e compilado em `build\n2-sdk-multi`;
  o binario `rexglue` e o help real foram verificados. A toolchain local e
  LLVM/Clang 23.1.4 x64, Windows SDK RC
  `10.0.26100.0\x64\rc.exe`, C++23 e flags `-march=x86-64-v2`, como no preset
  `win-amd64` do SDK. O build do SDK terminou em 622 acoes.
- Os 22 submodulos do SDK e a dependencia recursiva foram restaurados nos
  commits fixados. As arvores Git do SDK/libmspack estavam limpas depois de
  cada tentativa. No checkout Windows, 15 links simbolicos do libmspack aparecem
  como arquivos-placeholder; foram temporariamente substituidos por hardlinks
  aos destinos presentes durante builds e restaurados em `finally`. A verificacao
  posterior confirmou os 15 placeholders byte a byte.
- `src\neverdead_manifest.toml` foi criado pelo `rexglue init`. O arquivo
  `src\neverdead_config.toml` acrescenta dois limites de funcao inferidos de
  disassembly PowerPC big-endian e fronteiras `.pdata`, para corrigir tres
  branches tail nao resolvidos na primeira validacao:
  - `0x8225C0C8` e `0x825D579C` branch para `0x8225BCA0`. O corpo de cinco
    instrucoes termina em `blr` em `0x8225BCB0`, ocupa `0x14` bytes e o proximo
    inicio `.pdata` e `0x8225BCB8`.
  - `0x82564B7C` branch para `0x82564A40`. O corpo termina em `blr` em
    `0x82564AB4`, ocupa `0x78` bytes e o proximo inicio `.pdata` e
    `0x82564AB8`.
  Os tamanhos sao hints explicitos baseados nas instrucoes e limites observados,
  nao stubs nem simbolos arbitrarios.
- A segunda execucao do codegen completou `Validate` e `Write` sem erros:
  `FunctionGraph::sealAllReady` selou 24.407 funcoes, 0 sem selagem; o mapa
  distribuiu 24.407 enderecos em 104 particoes. Foram escritos 215 artefatos
  gerados, incluindo 104 fontes `neverdead_recomp.N.cpp`, `neverdead_init.cpp`
  e `neverdead_register.cpp`. O conjunto `.cpp` soma 110.068.038 bytes.
- O shard `neverdead_recomp.8.cpp` contem 212 definicoes `DEFINE_REX_FUNC`,
  incluindo o candidato de smoke `sub_823C1A70`. O CMake compilou esse shard
  com sucesso para
  `build\n2-neverdead\CMakeFiles\neverdead_recomp.dir\generated\default\neverdead_recomp.8.cpp.obj`
  (810.249 bytes). O PCH foi compilado na mesma build.
- A configuracao CMake isolada em `build\n2-neverdead` concluiu com Clang e
  ReXGlue SDK local. A primeira tentativa nao encontrou RC; a repeticao incluiu
  o caminho do compilador de recursos. A primeira build do shard falhou ao
  compilar um placeholder de symlink do libmspack; depois de materializar
  temporariamente os links, a compilacao apontou a falta de
  `-march=x86-64-v2`. A build seguinte aplicou as flags C/C++ do preset do SDK
  e compilou o objeto. Os logs de cada tentativa foram preservados.

## Resultado por marco

| Marco | Resultado |
|---|---|
| A - Ler XEX e construir mapa | Concluido para o mapa estatico do ReXGlue; validacao de codegen passou. |
| B - Gerar C++ | Concluido para 24.407 funcoes descobertas e 104 particoes. |
| C - Compilar subconjunto | Concluido: 212 funcoes do shard 8 foram compiladas a objeto. Nenhum teste de equivalencia foi executado. |
| D - Compilar executavel integral | Nao iniciado; apenas um shard foi compilado. |
| E - Iniciar runtime | Nao iniciado. |

Nao ha contagem confiavel de funcoes ainda pendentes no grafo do XEX, nem prova
de equivalencia funcional. Codegen bem-sucedido e compilacao de um shard nao
demonstram build integral, boot, renderizacao ou jogabilidade.

## Logs e artefatos

- Configuracao e codegen: `logs\n2-codegen-retry01-cli.log`,
  `logs\n2-codegen-retry01-console.log`.
- Configuracao/build de projeto: `logs\n2-project-configure.log`,
  `logs\n2-project-configure-retry01.log`,
  `logs\n2-project-configure-retry02.log`.
- Tentativas de compilacao e erros iniciais de link-placeholder/flags:
  `logs\n2-smoke-shard-build.log`,
  `logs\n2-smoke-shard-build-retry01.log`,
  `logs\n2-smoke-shard-build-retry02.log`.
- Build/configuracao do SDK e CLI: `logs\n2-sdk-configure-final.log`,
  `logs\n2-sdk-build-retry.log`, `logs\n2-rexglue-help.log`,
  `logs\n2-sdk-install.log`.
- Fontes geradas e mapa: `src\generated\default\`,
  especialmente `codegen.partition.json` e `sources.cmake`.
- Limites manuais de funcao: `src\neverdead_config.toml`; o manifesto inclui
  esse arquivo por `includes`.

Uma tentativa de instalacao do SDK foi interrompida porque `SDL3_test.lib`
nao existia na arvore de build; o diretorio parcial criado por essa tentativa
foi removido. A compilacao do shard nao dependeu dessa instalacao. Nenhum
binario de jogo foi alterado. Nenhum executavel NeverDead foi linkado nem
executado.

## Proximo gate

Executar testes de equivalencia do shard/candidatos simples, caso exista um
harness confiavel, ou compilar e linkar o executavel completo em uma etapa
separada. Antes de alegar comportamento de jogo, ainda sera necessario resolver
imports/HLE e os requisitos de runtime; Xenos/renderizacao tambem nao foi
validada.
