# N0 - Auditoria do bootstrap NeverDead

Data: 2026-10-21. Raiz: `C:\projetos\neverdead`.
Escopo: arquivos locais e ferramentas instaladas; sem downloads, reclones,
checkout, inicializacao de submodulos, commits ou criacao do projeto do jogo.

## Resultado e limites

**FATOS VERIFICADOS:** os 13 HEADs existem, coincidem integralmente com
`references.csv` e com `git_inventory_fixed.csv`; os 13 worktrees estavam limpos,
incluindo a verificacao de arquivos nao rastreados. Todos os comandos
`git -C <repo> rev-parse --verify HEAD` terminaram com codigo 0.
O manifesto foi corrigido de `GitMetadataFailed` para `OK`, sem mudar commits,
URLs, grupos, nomes ou caminhos. Aqui `OK` significa **HEAD validado**, nao
"dependencias completas" ou "compila".

Ha **88 submodulos declarados e nao inicializados**: prefixo `-` em
`git submodule status --recursive`. Codigo de saida 0 nesse comando nao significa
que os submodulos estejam prontos. Nao e possivel enumerar os submodulos
transitivos dentro de um submodulo ausente: 88 nao e o total final de dependencias.

`src`, `build`, `generated`, `tests` e `game-dump` estavam vazios, inclusive entradas
ocultas; nenhum XEX, asset ou build de NeverDead foi encontrado nessas pastas.
**Nao houve codegen, compilacao, boot, renderizacao ou teste de jogabilidade de
NeverDead.** N0 valida o inventario, nao qualquer desses marcos.

**HIPOTESE:** `GitMetadataFailed` foi erro da etapa de coleta do bootstrap.
O script original e seu log nao estao na raiz nem em `logs` na inspeccao inicial;
portanto a causa exata dessa mensagem nao foi reproduzida nem corrigida no
bootstrap original. O defeito comprovado no manifesto foi reparado.

**RECOMENDACAO, AINDA NAO VALIDADA COM O JOGO:** usar o ReXGlue local como primeira
base PPC AOT + HLE + GPU Xenos, inicialmente D3D12 no Windows. Nao adicionar
XenonRecomp e XenosRecomp como dependencias obrigatorias desse caminho.
Um renderer HLE especifico de NeverDead e uma etapa posterior e distinta.

## 1. Mapa e inventario

```text
C:\projetos\neverdead\
  references.csv                 manifesto reparado
  git_inventory_fixed.csv        inventario anterior preservado
  src\                           vazio; sem projeto NeverDead
  build\                         vazio; sem CMakeCache ou executavel
  game-dump\                     vazio; sem dump para validar
  generated\                     vazio
  tests\                         vazio
  refs\
    core\                        rexglue-sdk, 360tools, XenonRecomp, XenosRecomp
    ports\                       DownpourRecomp, EdgeOfTimeRecomp,
                                 skate3recomp, UnleashedRecomp
    reverse-engineering\         xenia, XEXLoaderWV, pyghidra-mcp
    asura\                       RenegadeSquadron-PC, QuickBMS
  analysis\                      auditoria, inventarios e script N0
  logs\                          transcricoes e backup do manifesto
```

A raiz nao tem `.git`; cada referencia tem seu proprio repositorio.

| Repositorio relativo a `refs` | HEAD verificado | Submodulos ausentes |
|---|---|---:|
| `core\rexglue-sdk` | `c94f5ebdcb3c9d1a460ca48e04f9758448f8d518` | 22 |
| `core\360tools` | `1b53928767fa134c1ea2ea42007bc39852eea1fc` | 0 |
| `core\XenonRecomp` | `ddd128bcca99fe8bfbb99bea583c972351fa6ace` | 6 |
| `core\XenosRecomp` | `990d03b28a27b50277ee5d8d942e1c5f873869d1` | 5 |
| `ports\skate3recomp` | `f6e0ae87fdfecbadb5c1e36c55d66a744187a3cd` | 1 |
| `ports\DownpourRecomp` | `a183ff0b21f5e504526102754a04f2a9534a97b7` | 0 |
| `ports\EdgeOfTimeRecomp` | `340144e4c7979a9f46699bef368fe7d7c62fddc9` | 4 |
| `ports\UnleashedRecomp` | `cf829a9eca8fb680fba4b0409ddeb6ca92f22e3c` | 20 |
| `reverse-engineering\xenia` | `95a5c3ee250f80c3b9d139658649d9ffb6db3eec` | 30 |
| `reverse-engineering\XEXLoaderWV` | `4bcf58da4caa5260644fc19f5eef5ccde3b7ff46` | 0 |
| `reverse-engineering\pyghidra-mcp` | `42d8f80551a765441b1a723f6f1ff45aa3914d5e` | 0 |
| `asura\RenegadeSquadron-PC` | `3a27c97180475fa7aa2d6691da4b8fbe7037797a` | 0 |
| `asura\QuickBMS` | `5315ffe664b88dc09ae783ad17d9dfd252b1c927` | 0 |

### Evidencia persistente

Prefixo desta execucao: `analysis\n0-20261021-075433-051`.

| Arquivo | Conteudo |
|---|---|
| `*-repositories.csv` | HEAD, igualdade com pin, limpeza e contagem de submodulos por clone |
| `*-submodules.csv` | 88 caminhos, commits esperados e prefixos de estado |
| `*-files-sha256.csv` | **8.976 arquivos** locais rastreados, tamanho e SHA-256 |
| `*-workspace.csv` | Entradas imediatas das pastas de trabalho no momento da coleta |
| `logs\n0-20261021-075433-051.log` | Comandos Git por repo, resultados/codigos, versoes, presets e sondagens |
| `logs\n0-dependencies.log` | VS developer shell, binutils PPC e help Python |
| `logs\references-before-n0-20261021-075433-051.csv` | Manifesto original para rollback |

SHA-256 cobre os arquivos rastreados materializados nos 13 clones, nao os
diretorios `.git`, objetos Git, conteudo de submodulos ausentes ou arquivos
ignorados. SHA Git de commit e SHA-256 de arquivo sao identificadores diferentes.
Tambem foram procurados arquivos nas cinco pastas vazias do projeto; nao havia
artefatos do jogo para hashear. Os inventarios nao contem dumps nem chaves.

## 2. Matriz de reutilizacao

Os caminhos e intervalos abaixo sao relativos a raiz e ao HEAD da tabela.
"Implementado" significa codigo observado, nao execucao demonstrada nesta maquina.

### SDKs e ferramentas

| Capacidade | Evidencia local inspecionada | Reutilizacao e limite |
|---|---|---|
| Parser XEX/PE, compressao e patches | `refs\core\rexglue-sdk\src\system\xex_module.cpp:448-490,623-746,866-931` | ReXGlue ja le imagem XEX e PE, descomprime e carrega; nao escrever outro loader. Validar formato real do dump antes de escolher extracao. |
| Imports e simbolos | `refs\core\rexglue-sdk\src\system\xex_module.cpp:1059-1170`; `refs\core\rexglue-sdk\src\system\function_dispatcher.cpp:319-332` | Imports por biblioteca/ordinal e registro de funcoes/modulos existentes. Inventario de imports de NeverDead ainda nao existe. |
| PPC para C++ | `refs\core\rexglue-sdk\src\codegen\codegen.cpp:27-90`; `refs\core\rexglue-sdk\src\codegen\project_recompiler.cpp:254`; `refs\core\rexglue-sdk\src\codegen\builders\` | Pipeline de config, runtime em tool mode, analise e escrita. Reutilizar analise/emissao; corrigir hints somente com evidencia do binario. |
| CLI e modelo de projeto | `refs\core\rexglue-sdk\src\rexglue\commands\init_command.cpp:564-633`; `refs\core\rexglue-sdk\src\rexglue\commands\codegen_command.cpp:222-233` | `init`, `init module`, `codegen`, `--project-name`, `--xex-path`, `--game-root`, `--project-root`, `--target` observados no registro da CLI. Executavel nao esta disponivel; conferir help apos build. |
| Hooks do host e callbacks guest | `refs\core\rexglue-sdk\include\rex\rex_app.h:94-185`; `refs\core\rexglue-sdk\src\system\function_dispatcher.cpp:37-125` | Hooks de paths/setup/load/launch e dispatcher para chamadas guest/cross-module. Ha FIXME para argumentos em stack acima de oito: floats e 64 bits precisam de atencao; nao assumir ABI irrestrita. |
| HLE/kernel | `refs\core\rexglue-sdk\src\kernel\kernel_init.cpp:25-34`; `refs\core\rexglue-sdk\src\kernel\xboxkrnl\xboxkrnl_threading.cpp:1408-1480` | Xboxkrnl/XAM/XBDM e servicos existentes. Tambem ha exports marcados STUB: runtime presente nao significa cobertura total. Classificar os imports reais antes de preencher lacunas. |
| Renderer Xenos integrado | `refs\core\rexglue-sdk\src\graphics\CMakeLists.txt:1-106`; `refs\core\rexglue-sdk\CMakeLists.txt:34-48` | Plugin `rexgpu-xenos`, command processor, caches, tradutores DXBC/SPIR-V e backends D3D12/Vulkan. CPU e AOT; GPU usa camada de compatibilidade/emulacao Xenos. Isso nao e renderer HLE especifico do motor. |
| Testes ReXGlue | `refs\core\rexglue-sdk\tests\unit\CMakeLists.txt:3-45,70-79`; `refs\core\rexglue-sdk\tests\ppc\CMakeLists.txt:25-43,103-113`; `refs\core\rexglue-sdk\cmake\ppc_test_pipeline.cmake:7-28` | Catch2/CTest, memoria, imports, dispatcher, codegen e instrucoes PPC via assembler. `REXGLUE_BUILD_TESTS` e OFF por padrao. Suites nao foram compiladas/executadas em N0. |
| 360tools: triagem/orquestracao | `refs\core\360tools\README.md:17-54`; `refs\core\360tools\tools\harness\README.md:9-26`; `refs\core\360tools\tools\harness\recomp_harness.py:40-47` | Helpers Python e harness por estagio, nao outro runtime. Defaults apontam para discos e VS2022 de outra maquina; nao executar `run` sem adaptar caminhos. Auto-hints sao hipoteses de triagem, nao prova de fronteiras corretas. |
| 360tools: exemplos | `refs\core\360tools\templates\README.md:12-21`; `refs\core\360tools\templates\overlay\src\game_app.reference.h:27-66` | Referencia de hooks e stubs. Nao copiar `dispatch_tolerance.cpp` nem `/force:multiple` para ocultar chamadas invalidas; contrariam o criterio fail-fast desta tarefa. |
| XenonRecomp alternativo | `refs\core\XenonRecomp\README.md` (Implementation Details, Usage, Tests, Building); `refs\core\XenonRecomp\XenonUtils\xex.cpp:1-12`; `refs\core\XenonRecomp\XenonUtils\symbol_table.h:5-31`; `refs\core\XenonRecomp\XenonTests\CMakeLists.txt:1-25` | Parser/simbolos, XenonAnalyse, PPC->C++ e testes derivados de Xenia. README explicita ausencia de runtime. Hooks weak/mid-asm nao implementam HLE/callbacks completos. Precisa runtime proprio ou integracao substancial; nao e substituicao plug-and-play do ReXGlue. |
| XenosRecomp alternativo | `refs\core\XenosRecomp\README.md` (Implementation Details, Usage); `refs\core\XenosRecomp\XenosRecomp\shader_recompiler.cpp:77,1101`; `refs\core\XenosRecomp\XenosRecomp\main.cpp:32-73` | Tradutor de shaders para HLSL/cache DXIL-SPIR-V; nao command processor, memoria, EDRAM ou renderer completo. Tem assumptions de Unleashed, reflection obrigatoria e recursos nao implementados. Nao substituir o backend integrado antes de caracterizar shaders de NeverDead. |

### Ports: implementacao real versus descricao

| Referencia | Arquivos inspecionados e evidencia | O que aproveitar / nao transportar |
|---|---|---|
| DownpourRecomp | `refs\ports\DownpourRecomp\CMakeLists.txt:77-113`; `refs\ports\DownpourRecomp\downpour_manifest.toml:3-19`; `refs\ports\DownpourRecomp\src\downpour_app.h:115,165-180` | Exemplo mais direto de shell ReXGlue com paths/instalacao e GPU SDK. CMake define `DPOUR_NO_NATIVE_RENDER=1` e declara renderer nativo aposentado; nao usa renderer nativo como baseline atual. Manifesto fixa SDK `0.8.2.19`; README menciona fork com fixes manuais de 0.10. `generated\rexglue.cmake` falta neste clone e nao ha submodulo SDK: checkout sozinho nao fecha o build. Nao transplantar enderecos/patches UE3. |
| EdgeOfTimeRecomp | `refs\ports\EdgeOfTimeRecomp\reeot_manifest.toml:3-29`; `refs\ports\EdgeOfTimeRecomp\generated\rexglue.cmake:7-25`; `refs\ports\EdgeOfTimeRecomp\CMakeLists.txt:19-30,204-220`; `refs\ports\EdgeOfTimeRecomp\src\gpu\device.cpp:88-90,1111-1116`; `refs\ports\EdgeOfTimeRecomp\src\gpu\draw.cpp:2454,3099-3138` | SDK 0.10.0, modulo guest `GameLogic.dll`, renderer plume D3D12/Vulkan e fork XenosRecomp. Bom exemplo multi-modulo e shader cache. **Docs contraditorias:** `docs\BUILDING.md:3-4` diz que renderer nao foi publicado, mas `src\gpu` contem implementacoes de device/draw/replay. Presenca de fonte nao prova que o checkout publica tudo necessario nem que renderiza. `docs\RENDERER.md`, linkado no README, nao existe. Usar codigo/CMake como evidencia, nao promessa do README. |
| skate3recomp | `refs\ports\skate3recomp\cmake\CodegenTargets.cmake:1-36`; `refs\ports\skate3recomp\cmake\RexGlue.cmake:1-24`; `refs\ports\skate3recomp\src\skate3_native_render.cpp:1-32,67-90`; `refs\ports\skate3recomp\.gitmodules:1-4` | Exemplo `generate-all`, dois modulos e hooks de captura de cena; renderer proprio e fallback SDK documentados. SDK vem de **fork** `mchughalex/rexglue-skate3`, pin `7eb0faf7787f5e01333c228b8e3f03c32f7295ea`, nao do core local. Nao assumir compatibilidade nem copiar codigo sem esclarecer licenca do port. |
| UnleashedRecomp | `refs\ports\UnleashedRecomp\UnleashedRecompLib\CMakeLists.txt:13-97`; `refs\ports\UnleashedRecomp\UnleashedRecomp\kernel\imports.cpp:20-85`; `refs\ports\UnleashedRecomp\UnleashedRecomp\gpu\video.cpp:1-85`; `refs\ports\UnleashedRecomp\CMakeLists.txt:1-10` | Pipeline XenonRecomp + XenosRecomp, HLE/kernel/threading proprios, shaders e renderer especificos. Util para estudar arquitetura e paridade; codigo GPL precisa decisao de licenciamento antes de incorporacao. Nao usar seu runtime como se viesse no XenonRecomp. `VCPKG_ROOT` obrigatorio. |

### Comparacao dos pins: evitar misturar geracoes

O SDK core declara piso **0.10.0**, Clang >=18 e **C++23**
(`refs\core\rexglue-sdk\CMakeLists.txt:10-12,82-105`). O README/overlay do
360tools mira 0.8.0 e seu exemplo de preset nao corresponde ao configure preset
do SDK atual. Neste checkout o SDK configura com **`win-amd64`** e compila/testa
com **`win-amd64-release`**, por ser Ninja Multi-Config.

Unleashed fixa XenonRecomp em
`c5bfd90d87f2ed0db8cff5c19ea3aff0e161e527`, diferente de
`refs\core\XenonRecomp` (`ddd128bc...`). Seu XenosRecomp fixa `990d03b2...`,
igual ao core. Edge fixa XenosRecomp `a031503b...`, diferente do core.
Os pins sao comprovados pelo inventario de submodulos e pelos `.gitmodules`;
conteudo de forks/commits ausentes nao foi comparado como se estivesse local.
Sem inicializacao desses pins, nenhuma equivalencia de API e garantida.

### Referencias auxiliares e licencas

| Referencia | Evidencia / uso | Licenca observada |
|---|---|---|
| ReXGlue | `refs\core\rexglue-sdk\LICENSE:1-21` | BSD-3-Clause; preservar atribuicoes Xenia e terceiros. |
| 360tools | `refs\core\360tools\LICENSE:1-21`; `README.md` (License) | MIT; excecoes por arquivo, inclusive extrator STFS BSD-2-Clause. |
| XenonRecomp / XenosRecomp | `refs\core\XenonRecomp\LICENSE.md:1-22`; `refs\core\XenosRecomp\LICENSE.md:1-22` | MIT; dependencias separadas. |
| Downpour / Edge | `refs\ports\DownpourRecomp\LICENSE:1-22`; `refs\ports\EdgeOfTimeRecomp\LICENSE:1-22` | BSD-3-Clause; forks e dependencias exigem inventario proprio. |
| Unleashed | `refs\ports\UnleashedRecomp\COPYING:1-5` | Texto GPLv3; verificar cabecalhos/termos por arquivo antes de copiar ou vincular. |
| xenia | `refs\reverse-engineering\xenia\README.md`; `LICENSE:1-23` | BSD-3-Clause; referencia de comportamento/HLE/GPU, nao trocar o objetivo por JIT. |
| XEXLoaderWV | `refs\reverse-engineering\XEXLoaderWV\README.md:1-27,35-60` | Loader Ghidra com PDB/XDB/XEXP. Nenhuma LICENSE na raiz observada; conferir termos por arquivo antes de reutilizar. JDK/Gradle dependem do Ghidra escolhido. |
| pyghidra-mcp | `refs\reverse-engineering\pyghidra-mcp\pyproject.toml:1-14`; `LICENSE:1-4` | Apache-2.0; ferramenta auxiliar, Python >=3.10 e dependencias proprias. Ghidra/JDK nao validados em N0. |
| RenegadeSquadron-PC | `refs\asura\RenegadeSquadron-PC\README.md:1-8,126-129` | Port **PSP**, nao Xenon/Xenos; apenas pista de motor Asura, nao prova de formato/ABI comum com NeverDead. Nenhuma LICENSE na raiz observada; nao inferir que MIT do framework cubra todo o port. |
| QuickBMS | `refs\asura\QuickBMS\LICENSE:1-5`; `readme.md` | Texto GPLv2 e licencas de bibliotecas distintas. Ferramenta potencial para archives; nenhum extrator especifico de NeverDead foi validado. |
| skate3recomp | Arquivos da raiz, `.gitmodules` e README inspecionados | Nenhuma LICENSE/COPYING na raiz observada. Bloquear copia ate esclarecer permissao; fonte publica nao equivale a licenca de reutilizacao. |

Nao houve incorporacao de codigo de terceiros nesta etapa. Esta triagem de
licencas nao substitui auditoria das dependencias transitivas, FFmpeg/binutils
ou de cada arquivo que venha a ser distribuido.

## 3. Dependencias Windows e build

| Item | Observacao executada | Diagnostico |
|---|---|---|
| Windows | `OSDescription`: Windows `10.0.26300` | Arquitetura alvo Windows x64; nao inferir edicao comercial a partir do numero NT. |
| Git | `git --version`: `2.54.0.windows.1` | Operante; HEAD/status/submodule em todos os clones. |
| CMake | `cmake --version`: `4.4.4` | Supera piso 3.25 do ReXGlue; cinco arquivos de presets aceitos por `--list-presets=all`, codigo 0. Configuracao completa ainda nao executada. |
| Ninja | `ninja --version`: `1.13.2` | Encontrado no PATH; necessario para presets atuais. |
| Python | `python --version`: `3.14.6` | Harness `--help` retorna 0; `tomllib` existe. `Crypto`, `toml` e `tomli` nao estao nesse interpretador. `requirements.txt` do 360tools exige `pycryptodome>=3.15`; nao necessario para todos os helpers. Nao foi instalado nada globalmente. |
| VS | vswhere encontra Professional e BuildTools `18.10.12224.181` | VS **2026**, nao VS2022 como nos exemplos antigos. Ambos anunciam componente VC x86/x64; compatibilidade do build SDK ainda pendente. |
| MSVC / MSBuild | `vcvars64.bat`, `where cl/link/rc/msbuild`, `cl /?`: codigo 0 | `cl` 19.51.36260, MSVC tools 14.51.36231; compilador nao esta no PATH inicial. **MSVC nao substitui Clang**: SDK rejeita outro compiler ID. |
| LLVM / Clang | `Get-Command clang, clang++, clang-cl`; sondagem de `C:\Program Files\LLVM` e componentes LLVM dos dois VS | Nao encontrado nos locais sondados. VS tem clang-format/clang-tidy, nao clang compilador nesses diretorios. Bloqueio imediato para configurar o SDK; nao prova ausencia em todos os discos. |
| Windows SDK | `10.0.26100.0`, `d3d12.h`, UCRT e `rc.exe` encontrados | Headers e ferramentas presentes; link/execucao D3D12 ainda nao comprovados. |
| GPU | CIM: NVIDIA RTX 5060 Laptop, Intel UHD; drivers registrados no log | Enumeracao nao comprova feature levels, ROV, swapchain, Vulkan ou selecao do adaptador correto. |
| Vulkan / vcpkg | `VULKAN_SDK` e `VCPKG_ROOT` ausentes do ambiente | Nao implica ausencia de driver Vulkan. Vulkan headers/loader podem vir do SDK; vcpkg nao e requisito central do ReXGlue, mas e exigido pelo CMake raiz de Unleashed. |
| PPC binutils | as/ld/nm locais: `--help` e `--version`, todos codigo 0; GNU Binutils 2.24 | Ferramentas/Cygwin DLLs do SDK materializadas e executaveis; montagem dos testes PPC ainda nao exercitada. Nao baixar toolchain duplicado. |
| SDK compilado | `rexglue` nao encontrado no PATH; nenhum build em `build` | Fonte disponivel, ferramenta nao pronta. Nenhum codegen possivel nesta etapa sem resolver build/SDK externo. |
| Disco | Aproximadamente 36 GiB livres em C: durante a coleta | Reserva limitada para submodulos, dump, codegen, PDB e caches. Medir RAM/disco antes de paralelizar build; nao assumir que todo o fluxo cabe. |

Incidente de diagnostico: a primeira consulta `cl /Bv` imprimiu versoes mas saiu
com D8003/codigo 2 por nao receber fonte; nao foi falha de compilacao do SDK.
O primeiro `vcvars64` tambem avisou que `vswhere.exe` nao estava no PATH.
A repeticao adicionou somente o diretorio Installer ao PATH **do processo**,
ativou o mesmo ambiente e executou `cl /?` com codigo 0 e sem aquele aviso.
Nenhuma configuracao global de PATH/VS foi alterada.

Nao se executou configure/build do SDK: o Clang nao foi localizado e
`thirdparty\CMakeLists.txt:33-73` falha explicitamente com submodulos ausentes.
Dar sucesso a `--list-presets` nao substitui configurar, compilar ou executar.
O C++20 solicitado inicialmente nao atende este SDK; usar C++23 no caminho
ReXGlue e manter o limite de linguagem documentado.

## 4. Lacunas e bloqueios

1. Dump legal ausente: falta `default.xex`, arvore de assets, regiao/versao e
   possivel TU. Nao se conhece Title ID, entrypoint, imports, funcoes, DLLs ou
   shaders de NeverDead. Nao reutilizar enderecos de outros jogos.
2. Clang/LLVM nao localizado e 22 submodulos diretos do SDK ausentes. Restauro
   deve respeitar os pins, nao `--remote` nem reclone. Dependencias transitivas
   so poderao ser contabilizadas depois.
3. Nenhum projeto/config de NeverDead, SDK build, codegen ou suite de testes
   executada. Os arquivos gerados de outros ports nao atestam o nosso titulo.
4. Compatibilidade Asura, instrucoes VMX128, exceptions/SEH, TLS, callbacks,
   sincronizacao, MMIO, audio e streaming precisam de evidencia do jogo.
   Dispatcher ja tem limitacao de ABI anotada; HLE contem stubs.
5. Renderer SDK e renderer HLE do motor sao alternativas em estagios diferentes.
   Sem capturas/shaders nao ha base para estimar paridade ou escolher hooks HLE.
6. Licencas nao esclarecidas de alguns ports, forks ausentes e commits diferentes
   impedem copia direta indiscriminada. Definir licenca do projeto antes de integrar.
7. Sem scripts/logs originais do bootstrap, somente manifesto pode ser reparado
   de maneira comprovada. A raiz sem Git tambem nao oferece rollback por commit.

## 5. Roadmap incremental e criterios de passagem

Todos os comandos desta secao sao **planejados, nao executados em N0**.
Precondicoes devem ser cumpridas antes de avancar; nao criar stubs que retornem
sucesso para passar o marco seguinte.

| Marco | Acao executavel / evidencia a guardar | Criterio objetivo | Risco e contencao |
|---|---|---|---|
| N1a - SDK restaurado | Disponibilizar LLVM Clang >=18, preferencialmente 20+ como no playbook; Developer Shell com SDK Windows. `git -C .\refs\core\rexglue-sdk submodule update --init --recursive` e nova coleta de HEAD/status/hashes. | `clang --version` e `clang++ --version` funcionam; submodulos requeridos sem `-`, `+` ou `U`; HEAD core permanece `c94f5ebd...`. | Downloads/espaco e symlinks libmspack: comparar conteudo real antes de materializar, nao aplicar workaround antigo cegamente. Nao restaurar os 88 de todos os ports sem necessidade. |
| N1b - Ferramenta e testes do SDK | Dentro do SDK: `cmake --preset win-amd64 -DREXGLUE_BUILD_TESTS=ON`; `cmake --build --preset win-amd64-release --target rexglue unit_tests ppc_tests --parallel 2`; `ctest --preset win-amd64-release --output-on-failure`. | Configure/build/testes terminam com codigo 0, numero de testes descobertos >0, logs preservados. Localizar exe, rodar `--help`, `init --help`, `codegen --help`. | VS2026/CMake4 podem expor incompatibilidades. Corrigir causa em mudanca isolada com diff, nao relaxar ABI ou ignorar testes. |
| N2 - Dump identificado | Copia legal em `game-dump`, inventario relativo/tamanho/SHA-256, classificacao XEX/PE/archives e TU; leitura inicial com ferramentas cujo help/uso foi confirmado. | XEX abre com o loader escolhido; regiao, imagem/base/entrypoint/imports/modulos e hashes ficam registrados localmente. | Dump alterado, patch de regiao errada ou export de assets/chaves. Manter originais somente leitura e fora de versionamento. |
| N3 - Somente codegen | Com CLI confirmada: `rexglue init --project-name neverdead --xex-path .\game-dump\default.xex --game-root .\game-dump --project-root .\src`; inspecionar manifesto gerado e depois `rexglue codegen` dentro de `src`. | Saida 0, lista de unidades C++/sources e imports gerada, entradas/targets nao resolvidos contabilizados; hints sustentados por analise. | Relative paths e multi-modulo precisam conferir no manifesto antes do codegen. Sem TU comprovado, nao inventar patched_file_path. Artefatos ficam inicialmente no layout escolhido pelo init, nao mover manualmente para `generated` sem necessidade. |
| N4 - Compilacao NeverDead | Ler presets **gerados**, configurar e compilar com SDK pinado e simbolos de diagnostico. | Executavel e dependencias ligados, imports pendentes classificados, codigos 0 e hashes dos artefatos. | Link bem-sucedido pode esconder stubs. Sem uso de dispatch_tolerance/force-multiple para apagar falhas; cada implementacao temporaria precisa log, teste e criterio de remocao. |
| N5 - Boot | Rodar com dump configurado e capturar log, guest PC/thread, imports chamados e primeiro ponto observavel do fluxo real. | Entrada guest e inicializacao do titulo demonstradas, sem chamar uma janela vazia de boot concluido. Definir o ponto de controle concreto apos N2. | Deadlocks, TLS, exceptions e callbacks; resolver um primeiro bloqueio por vez com reproducao. |
| N6 - Primeiro frame correto | Comecar pelo plugin Xenos SDK D3D12; guardar captura/log de draws, shaders, texturas, depth/EDRAM/resolve e referencia visual do mesmo trecho. | Frame do jogo identificado e comparavel, nao apenas clear/swapchain. | Shaders nao cobertos, endian/tiling, formato HDR e adapter. Vulkan e comparacao posterior; nao trocar de renderer para mascarar bug. |
| N7 - Paridade e jogabilidade | Cena controlada, input, audio, streaming, save/load, transicao e QA reprodutivel. So depois avaliar renderer HLE especifico do Asura com costuras comprovadas. | Cenarios nomeados passam com logs/capturas, saves persistentes e inventario de limitacoes. "Jogavel" exige percurso e controles, nao somente menu. | Timing/fisica e efeitos em cenas tardias; manter baseline fiel antes de liberar FPS/resolucao/renderer novo. |

N1b independe do dump. N2 pode ocorrer em paralelo ao preparo de ferramentas.
N3 depende de N1b+N2; N4 de N3; N5 de N4; N6 de N5; N7 de N6.
O **proximo marco verificavel e N1b**, nao "NeverDead recompilado".

## Mudancas, comandos e rollback

Mudancas exatas: adicionado `analysis\audit-n0.ps1`, este relatorio, inventarios e
logs N0; em `references.csv`, apenas os 13 campos `Status` mudaram para `OK`.
`git_inventory_fixed.csv`, fontes dos 13 repositorios e pastas do jogo/build
foram preservados. Nenhuma dependencia instalada, nem arquivo proprietario criado.

Execucao principal real: `.\analysis\audit-n0.ps1 -RepairManifest`, codigo 0.
O script registra por repositorio `rev-parse --verify HEAD`,
`status --porcelain=v1 --untracked-files=normal`, `submodule status --recursive`,
`show -s --format=%H %cI %s HEAD`, lista arquivos com `git ls-files` e calcula
`Get-FileHash -Algorithm SHA256`. Tambem executa versoes, help CMake e
`cmake -S <repo> --list-presets=all` nos cinco repos com presets.

Inspeccao adicional real: `Get-ChildItem`, leituras de README/CMake/manifests,
`vswhere -all -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64`,
sondagens `Get-Command`/`Test-Path`, `Get-CimInstance Win32_VideoController`,
binutils `--help`/`--version` e
`python -B .\refs\core\360tools\tools\harness\recomp_harness.py --help`.
Resultados detalhados estao nas duas transcricoes. Nenhum dos comandos de N1-N7
foi apresentado como resultado realizado.

Para repetir a coleta sem reparo: `.\analysis\audit-n0.ps1`. Cada execucao gera
novo prefixo com timestamp e nao substitui inventarios anteriores.
Para desfazer somente o reparo do manifesto, apos conferir que nao houve novas
edicoes, restaurar a copia
`logs\references-before-n0-20261021-075433-051.csv` sobre `references.csv`.
Nao ha necessidade de rollback/reclone dos repositorios.
