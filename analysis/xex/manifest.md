# NeverDead Xbox 360 - N1: XEX e arquitetura

## Resultado e limites

Foi localizado e analisado **um** `default.xex` em
`C:\projetos\NeverDeadxex`. O arquivo declara Title ID **0x4B4E081F**,
PowerPC big-endian e entry point **0x826D1288**. A carga AES/basic foi
decodificada para uma imagem privada, fora do dump e do workspace.
Isso comprova acesso a headers e instrucoes, **nao recompilacao de NeverDead**.
Nao houve codegen, build do jogo, boot, execucao de codigo guest ou renderizacao.

`inventory.json` e o inventario detalhado: hashes de todos os arquivos fornecidos,
claims classificadas, offsets/lengths no original ou derivado, fontes locais com
SHA256/linhas, SHAs Git das referencias, imports, secoes, .pdata e candidatos de
controle. Numeros de linhas referem-se aos arquivos locais nesses commits, nao a
versoes atuais da Internet. Dados de identidade abaixo sao declaracoes do binario;
nao autenticam a origem comercial do dump.

REA rejeitou primeiro XEX como formato nao suportado e depois o PE derivado pela
arquitetura COFF `0x01F2` nao suportada. Nenhuma sessao nativa REA abriu.
A evidencia restante vem do parser local, fontes dos loaders e GNU objdump PPC,
nao de uma decompilacao REA/Ghidra. Ghidra ainda nao foi executado.

## 1. Identidade e integridade observadas

| Campo | Valor verificado | Fonte no JSON |
|---|---|---|
| Original | `C:\projetos\NeverDeadxex\default.xex` | `original` |
| Tamanho | 9.580.544 bytes (`0x923000`) | `original.size` |
| SHA256 | `02d06295e67a61892e4bf55e6f50a647a059e7c71e3d9deb912edd29ef7aa2e1` | `original.sha256` |
| SHA1 | `6400b95e795ddd88e3b20147c89ca76688e8c56d` | `original.sha1` |
| Title ID / Media ID | `0x4B4E081F` / `0x5D5CA48B` | `claims: execution.*` |
| Versao / base | `0.0.0.9` / `0.0.0.9` (ambas raw `9`) | `claims: execution.*version` |
| Regiao | mascara `0xFFFFFFFF`: todos os bits de regioes habilitados | `claims: xex.region_mask` |
| Midia | allowed media `0x4` (DVD/CD); image flags `0x8` (XGD2 media only) | `claims: xex.allowed_media/image_flags` |
| Disco / plataforma / tabela | disco 1 de 1; plataforma 0, executable table 0 | `execution.platform_table_discs` |
| Nome PE declarado | `default.exe` | `xex.original_pe_name` |
| Timestamp COFF declarado | `2011-11-06T02:37:16Z` | `pe.coff` |
| Escopo do dump | 429 arquivos; 6.711.402.803 bytes | `dump_inventory` |

**TU nao determinado.** Nao foram encontrados arquivos `.xexp` ou nomes de
arquivo com prefixo TU numerico/separado. Versao igual a base e ausencia desses
nomes nao demonstram TU0; o ultimo componente `9` nao significa TU9. A mascara de
regiao tambem nao identifica SKU/release. Faltam autenticacao RSA, catalogo de
dump confiavel e identificacao oficial de updates.

O hash simples de cada faixa expandida foi comparado experimentalmente aos
digests dos 193 descritores de paginas: **0 matches**. Essa comparacao nao foi
validada como algoritmo/escopo de autenticacao XEX; nao prova corrupcao,
adulteracao nem validade. Os descritores cobrem exatamente `0xC10000` bytes.
Os hashes SHA256 do arquivo e da imagem sao identificadores reproduziveis,
nao substitutos de autenticacao.

## 2. Container, PE e memoria

XEX2, module flags `1`, 16 optional headers, payload em `0x3000`, security info
em `0x98` (tamanho declarado `0x139C`). File-format info em `0x1448`:
encryption **1 (AES-CBC normal)**, compression **1 (basic data/zero runs)**.
Nao e LZX. A reconstrucao seguiu
`refs\core\rexglue-sdk\src\system\xex_module.cpp:536-621`.

| Bloco | Bytes presentes no payload | Zeros inseridos |
|---|---:|---:|
| 0 | 1.671.168 | 32.768 |
| 1 | 6.455.296 | 32.768 |
| 2 | 819.200 | 3.014.656 |
| 3 | 622.592 | 0 |

A imagem resultante possui 12.648.448 bytes (`0xC10000`) e SHA256
`0425bbb23adddd342e2bf0e758884db12aa614a652cd38db262a899ffc9c422c`.
O adaptador usa a referencia existente apenas em memoria; nao introduz literais
de chaves nem grava material de sessao. A imagem privada nao foi copiada ao
workspace. Nenhum loader foi usado para modificar o original.

O PE tem assinatura MZ/PE, e_lfanew `0xF0`, machine
`IMAGE_FILE_MACHINE_POWERPCBE = 0x01F2`, PE32 magic `0x10B`, optional header
224 bytes, characteristics `0x102`, subsystem **14 (Xbox)**.
COFF symbols pointer/count sao zero; CLR directory e vazio.

| Memoria declarada | Valor |
|---|---|
| Load address / PE image base | `0x82000000` |
| XEX entry / PE entry RVA | `0x826D1288` / `0x006D1288` |
| XEX mapped range | `[0x82000000, 0x82C10000)` |
| PE SizeOfImage | `0xCBF200`, diferente do tamanho XEX |
| Section / file alignment | `0x10000` / `0x200` |
| PE headers size | `0x600` |
| XEX default stack / PE reserve / commit | `0x40000` em todos os tres |
| XEX default heap header | ausente |
| PE heap reserve / commit | `0x100000` / `0x1000` |
| TLS | 64 slots; raw address, data size e raw size = 0 |
| System flags | `0x200` (voice channel) |

Esses campos nao estabelecem consumo total de RAM/VRAM: alocacoes dinamicas,
memoria fisica, buffers GPU e assets ainda nao foram medidos.
A divergencia de SizeOfImage permanece sem explicacao demonstrada.

### Secoes PE

Valores em hexadecimal. **A imagem derivada ja esta em layout carregado:**
`offset = VA - 0x82000000 = RVA`. `PointerToRawData` e legado e nao deve ser usado
como offset para carregar esta imagem. Exemplo: `.text` deve ser lida em
`0x1B2200`, nao em `0x1A8000`.
Isso e corroborado pelo SDK (`xex_module.cpp:796-833`) e por
`XEXLoaderWV\XEXLoaderWV\src\main\java\xexloaderwv\XEXHeader.java:424-431`.

| Secao | RVA | VirtualSize | Raw pointer legado | Raw size legado | Flags |
|---|---|---|---|---|---|
| .rdata | 000600 | 16F080 | 000600 | 16F200 | 40000040 |
| .pdata | 16F800 | 0238D0 | 16F800 | 023A00 | 40000040 |
| BINKCONS | 193200 | 0029C0 | 193200 | 002A00 | 40000040 |
| RADCONST | 195C00 | 000044 | 195C00 | 000200 | 40000040 |
| BINK | 1A0000 | 011540 | 195E00 | 011600 | 60000020 |
| RADCODE | 1B1600 | 000AFC | 1A7400 | 000C00 | 60000020 |
| .text | 1B2200 | 60E3E4 | 1A8000 | 60E400 | 60000020 |
| BINKBSS | 7D0000 | 005B18 | 000000 | 000000 | C0000080 |
| .data | 7D5C00 | 3A61B8 | 7B6400 | 0C1200 | C0000040 |
| BINKDATA | B7BE00 | 002B70 | 877600 | 002C00 | C0000040 |
| RADDATA | B7EA00 | 000024 | 87A200 | 000200 | C0000040 |
| .XBMOVIE | B7EC00 | 00000C | 87A400 | 000200 | C0000040 |
| .idata | B80000 | 0004AC | 87A600 | 000600 | C0000040 |
| .XBLD | B90000 | 000110 | 87AC00 | 000200 | 42000040 |
| .reloc | B90200 | 062D70 | 87AE00 | 062E00 | 42000040 |

**Exports:** security export VA = 0, PE export directory = `(0,0)` e optional
header exports-by-name ausente. Nao ha tabela de exports declarada nesses
mecanismos; isso nao elimina callbacks por endereco, vtables ou ponteiros.

**Relocations nao resolvidas:** o diretorio PE declara RVA `0xB90200`,
tamanho `0x62D70`. No primeiro bloco, a leitura BE produz page RVA
`0x5223E92C`, block size `0xA99B3448`; LE produz `0x2CE92352`,
`0x48349BA9`. Ambas violam limites/alinhamento de blocos PE convencionais.
Nao foram recuperadas relocations validas, mas tambem nao foi provado que
inexistam ou que devam seguir essa codificacao. Nao fazer rebasing arbitrario:
preservar a base guest e investigar formato, descarte ou transformacao pelo
toolchain sem atribuir uma causa nao demonstrada.

## 3. Imports e dependencia real de Xbox 360

O bloco de imports em `0x2754` tem `0x8AC` bytes e duas bibliotecas.
Cada registro aponta para uma VA guest: seu conteudo **BE** fornece type/ordinal.
Os pares type 0 (value slot) e type 1 (thunk) foram associados por ordinal,
nao simplesmente por posicao consecutiva.

| Biblioteca | Registros | Imports unicos | Versao / minima |
|---|---:|---:|---|
| xam.xex | 190 | 95 | 2.0.20871.0 / 2.0.13599.0 |
| xboxkrnl.exe | 336 | 174 | 2.0.20871.0 / 2.0.13599.0 |

Total: **269 imports**, incluindo 12 variaveis sem thunk.
Todos os nomes foram resolvidos nas tabelas locais do ReXGlue e Xenia e
concordaram. O JSON inclui ordinal, slot, thunk, offsets, nomes e fonte/linha.
Nao ha outro `.xex`/`.dll` visivel na arvore fornecida, mas ainda nao se
procurou por modulos dentro de containers de assets.

Dependencias observadas incluem threads/APC/DPC, excecoes/unwind, filesystem,
carregamento dinamico, memoria fisica/MMIO, Vd/ring buffer/swap/callbacks,
audio, usuarios, rede e servicos XAM. Importar nao prova executar.
O scan de branches encontrou os seguintes **call sites estaticos candidatos**:

| Import | Thunk VA | Quantidade | Primeiro site |
|---|---|---:|---|
| ExCreateThread | 827BFCA4 | 3 | 826D334C |
| XexGetProcedureAddress | 827BFC54 | 16 | 826D28E0 |
| XexLoadImage | 827BFC64 | 1 | 826D2950 |
| XexLoadImageHeaders | 827BFB14 | 1 | 826CAB34 |
| RtlRaiseException | 827BF9A4 | 3 | 826C839C |
| RtlUnwind | 827C0564 | 2 | 8278DFD4 |
| MmMapIoSpace | 827C0474 | 1 | 8273727C |
| VdSwap | 827BFFD4 | 1 | 826B89A0 |
| NtWriteFileGather | 827BFD74 | 1 | 826D4C3C |

Esses sites devem ser ligados ao CFG de startup antes de se afirmar alcance ou
necessidade imediata. Chamadas indiretas nao entram nessa contagem.

### Lacunas HLE encontradas no SDK local

**33 imports** tem declaracao literal `REX_EXPORT_STUB` (15 XAM, 18 kernel).
A fonte/linha individual esta em `sdk_stub_declaration` no JSON:

- XAM: `NetDll_getsockname`, `NetDll_XNetCreateKey`,
  `NetDll_XNetRegisterKey`, `NetDll_XNetUnregisterKey`,
  `NetDll_XNetUnregisterInAddr`, `NetDll_XNetQosLookup`,
  `NetDll_XNetGetBroadcastVersionStatus`, `XNetLogonGetTitleID`,
  `XamUserGetMembershipTierFromXUID`, `XamUserGetOnlineCountryFromXUID`,
  `XamShowFriendsUI`, `XamShowMarketplaceUI`, `XamShowGamerCardUIForXUID`,
  `XamUserCreateStatsEnumerator`, `XamVoiceSubmitPacket`.
- Kernel: `IoCheckShareAccess`, `IoCompleteRequest`, `IoDeleteDevice`,
  `IoDismountVolume`, `IoInvalidDeviceRequest`, `IoRemoveShareAccess`,
  `IoSetShareAccess`, `MmLockAndMapSegmentArray`,
  `MmUnlockAndUnmapSegmentArray`, `NtWriteFileGather`, `ObIsTitleObject`,
  `ObReferenceObject`, `RtlUpcaseUnicodeChar`, `XAudioGetDuckerLevel`,
  `XAudioGetDuckerThreshold`, `XAudioGetDuckerAttackTime`,
  `XAudioGetDuckerReleaseTime`, `XAudioGetDuckerHoldTime`.

Isso nao e uma auditoria completa das implementacoes. Alem do macro,
`XexLoadImageHeaders_entry` loga "- stub" e retorna `X_STATUS_NOT_IMPLEMENTED`
em `refs\core\rexglue-sdk\src\kernel\xboxkrnl\xboxkrnl_modules.cpp:212-215`.
Ha um call site candidato para esse import; nao substitui-lo por sucesso falso.
Outros exports sem macro tambem podem ter suporte parcial.

As 17 entradas de static libraries identificam XAPILIB, D3DX9, XGRAPHC,
XBOXKRNL, XNET, LIBCPMT, XAPOBA, XAUDIO2, XMCORE, XMP, XONLINE, XHV2,
XPARTY, D3D9LTCG, LINK, C2 e C1. Versoes completas estao no JSON.
Nomes BINK/RAD e essas bibliotecas indicam middleware/runtime estatico;
nao estabelecem arquitetura interna do motor nem formato dos assets.

## 4. PPC, ABI e controle de fluxo

O container XEX, registros de imports e instrucoes sao big-endian; os
metadados PE sao little-endian. O entry decodifica como `mflr r12`, chamada
`bl 0x8278CD48`, preparacao de frame e `stwu r1,-496(r1)`.
Uso de r3 como argumento/resultado, stack em r1 e LR e visivel no trecho.
Ponteiros/VA guest sao de 32 bits, mas isso **nao** transforma Xenon em
um ABI desktop PPC32 nem restringe GPRs a 32 bits.
O SDK armazena GPRs de 64 bits e traduz argumentos inteiros r3-r10 e stack:
`include\rex\ppc\context.h:43-54`, `include\rex\ppc\function.h:104-134`.
Assinaturas completas, vetores/VMX128 e convencoes especiais por funcao
ainda precisam ser recuperados.

`.pdata` fornece **18.202 registros**, todos com inicio nas secoes executaveis;
**41** possuem ExceptionFlag, incluindo o entry. Interpretacao conforme
`src\codegen\phase_register.cpp:43-55` do SDK: prolog no byte baixo,
FunctionLength em instrucoes nos bits 8..29, ThirtyTwoBit no bit 30 e
ExceptionFlag no bit 31. Nao e prova de que todas as funcoes estao cobertas.

Scan de palavras alinhadas em BINK/RADCODE/.text: 86.782 `bl`, 37.825 `b`,
21.651 `bctrl`, 774 `bctr`. Pode incluir dados embutidos; nao e um CFG.
Nenhum match do padrao exato de island
`lis; addi/ori; mtctr; bctr` foi encontrado. Isso **nao** exclui veneers,
branch chains, tail calls ou outras formas de islands.

Os quatro padroes exatos comparados com XenonAnalyse nao deram matches.
Inspecao de `bctr` revelou a variacao real
`lis; rlwinm; addi; lwzx; mtctr; bctr`: **152 candidatos**, dos quais
150 tem bound candidato e todos os targets calculados dentro de secoes de
codigo. Ainda falta validar registros, bounds e CFG individualmente.
Distribuicao: 1 BINK, 1 RADCODE, 150 .text.

O caso em `0x821A9128` (BINK) foi inspecionado com objdump:
`cmplwi r11,9`, branch de limite, indexacao `r11*4` e tabela BE de 10 VAs
em `0x821A9140`, seguida de `mtctr/bctr`. A saida `-D` tambem interpreta
bytes da tabela como instrucoes: esses bytes devem ser marcados como dados,
nao recompilados indiscriminadamente. O primeiro candidato .text esta em
`0x821FC8CC`, tabela `0x821FC8E4`, bound candidato 12.

### Lista inicial para Ghidra, ainda nao executada

| Endereco / faixa | Questao e criterio de resolucao |
|---|---|
| 826D1288, 8278CD48 | Entry, save helper candidato e startup; recuperar grafo, frame e EH sem inventar nomes de funcao |
| 821A9128, 821B176C, 821FC8CC | Switches BINK/RAD/.text; confirmar index, bound, tabela e todos os destinos |
| 82539838, 826A28C0 | Dois switches sem bound encontrado na janela heuristica; recuperar limites pelo CFG |
| 821B1608, 823C1A00, 826DD520 | Primeiros exemplos com ExceptionFlag; identificar handlers e dados associados |
| 826E13E8, 826E19B8, 826E22B0, 826E25A8 | Mais funcoes EH; compatibilidade com unwind e callbacks do SDK |
| 826D28E0, 826D2950, 826CAB34 | Recuperar argumentos de GetProcedureAddress/LoadImage/LoadImageHeaders e modulos efetivamente solicitados |
| 8273727C, 826B89A0 | MMIO e swap: identificar parametros, memoria e dependencias Xenos |
| Todos os `ppc_scan.indirect_sites` | Classificar virtual calls, callbacks e tail calls; definir alvos admitidos para AOT |
| 82B90200 e PE SizeOfImage | Esclarecer relocations e diferenca de mapeamento sem alterar base como atalho |

Importar como Xbox PPC big-endian com loader adequado e preservar separadamente
bytes originais e memoria de analise. XEXLoaderWV altera thunks em memoria e
possui logging de material sensivel em certos caminhos: nao executar seu loader
sem revisar/sanitizar esses logs. Nao salvar chaves nem imagem proprietaria no repo.

## 5. Comparacao dos quatro parsers

| Implementacao | Evidencia realmente usada | Resultado / cuidado |
|---|---|---|
| ReXGlue | Leitura de `xex2_info.h`, `xex_module.cpp`, tabelas de exports e .pdata | Referencia principal para IDs, AES/basic, RVA carregado e imports por ordinal; executavel SDK nao compilado/executado |
| Xenia | Leitura de `kernel\util\xex2_info.h` e tabelas xam/xboxkrnl | Estruturas/IDs e 269 nomes concordam; loader Xenia nao executado |
| XEXLoaderWV | Leitura de `XEXHeader.java` e `NTHeader.java` | XEX BE/PE LE e leitura por RVA; altera thunks da memoria de analise e associa thunk ao registro anterior; nao executado |
| 360tools | `xex_info.py` e `parse_xex_imports.py` executados, exit 0; logs preservados | Campos semanticamente incorretos apesar de exit 0; nao usar como manifesto autoritativo |

Em 360tools, `xex_info.py:60-115` possui IDs errados: o log apresenta entry
`0x200` (system flags real), stack como heap e execution info como TLS.
`parse_xex_imports.py:155-208` le o baixo da VA como ordinal sem dereferenciar a
imagem: o primeiro import xam sai como `1536`, mas e `XNotifyGetNext`,
ordinal `651`; versao sai `32.81.34560` em vez de `2.0.20871.0`.
Nao foram alteradas fontes das referencias durante esta auditoria read-only.

Pins: SDK `c94f5ebdcb3c9d1a460ca48e04f9758448f8d518`,
360tools `1b53928767fa134c1ea2ea42007bc39852eea1fc`,
XenonRecomp `ddd128bcca99fe8bfbb99bea583c972351fa6ace`,
Xenia `95a5c3ee250f80c3b9d139658649d9ffb6db3eec`,
XEXLoaderWV `4bcf58da4caa5260644fc19f5eef5ccde3b7ff46`.

## 6. Bloqueadores e proximo marco

| Prioridade | Fato / risco | Porta de saida objetiva |
|---|---|---|
| Alta | EH no entry e outras 40 funcoes; destinos indiretos ainda incompletos | CFG de startup, metadados EH e targets documentados, incluindo switches; nao aceitar fallthrough silencioso |
| Alta | Carregamento dinamico e resolucao de exports com sites candidatos; apenas um modulo visivel | Identificar nomes/ordinais solicitados e origem de cada modulo necessario, inclusive containers |
| Alta | HLE parcial: 33 declaracoes stub e LoadImageHeaders NOT_IMPLEMENTED | Classificar chamadas alcancaveis e implementar comportamentos exigidos com erros explicitos; nao fingir sucesso |
| Alta | Dependencias Xbox graphics/MMIO/audio/threading | Planejar compatibilidade SDK/Xenos, sincronizacao e callbacks antes de prometer renderer nativo |
| Media | Layout carregado difere de PE raw; relocations e SizeOfImage nao esclarecidos | Fixar mapeamento guest correto e explicar divergencias antes de rebasing ou carregar com parser PE generico |
| Aberta | Autenticidade/TU e comparacao de digests nao estabelecidas | Validar esquema de integridade e referencia confiavel sem concluir adulteracao por heuristica |

Nao ha evidencia atual de uma impossibilidade absoluta de AOT, nem prova de que
todos os blocos sejam recompilaveis. O proximo marco e **analise de startup
fechada**, nao jogo compilado: validar entry/EH, dois switches sem bound,
destinos indiretos alcancaveis e carregamentos dinamicos. Depois disso, preparar
o ambiente SDK indicado em `analysis\N0-auditoria.md` (Clang e submodulos ainda
pendentes) e observar codegen real com diagnosticos preservados. Codegen,
compilacao, boot, renderizacao e jogabilidade permanecem marcos separados.

## 7. Arquivos, comandos e preservacao

Criados nesta etapa: `decode-for-analysis.ps1`, `inspect_xex.py`,
`test_inspect_xex.py`, `inventory.json` e este manifesto em `analysis\xex`.
Versoes intermediarias do JSON foram preservadas na pasta privada da sessao.
Nenhum arquivo do dump, fonte de referencia ou projeto nativo foi modificado.
O reparo anterior de `references.csv` pertence a N0 e esta documentado em
`analysis\N0-auditoria.md`; nao houve reclone, instalacao, download ou commit em N1.

Comandos utilizados, com a imagem privada identificada por `$image` para
legibilidade (o caminho completo e seu hash estao em `inventory.json`):

```powershell
python -m unittest discover -s analysis\xex -p test_inspect_xex.py -v
python analysis\xex\inspect_xex.py --dump-root C:\projetos\NeverDeadxex --image $image --output analysis\xex\inventory.json
python refs\core\360tools\tools\xex_info.py C:\projetos\NeverDeadxex\default.xex
python refs\core\360tools\tools\parse_xex_imports.py C:\projetos\NeverDeadxex\default.xex
.\refs\core\rexglue-sdk\tools\binutils\powerpc-none-elf-objdump.exe -D -b binary -m powerpc:common64 -M vmx128 -EB --adjust-vma=0x82000000 --start-address=0x826d1288 --stop-address=0x826d1348 $image
.\refs\core\rexglue-sdk\tools\binutils\powerpc-none-elf-objdump.exe -D -b binary -m powerpc:common64 -M vmx128 -EB --adjust-vma=0x82000000 --start-address=0x821a9110 --stop-address=0x821a9190 $image
```

A derivacao foi executada com `decode-for-analysis.ps1 -InputPath <original>
-OutputPath <imagem-privada>`. O adaptador recusa sobrescrita. A chave de
referencia nao aparece na linha de comando nem nos artefatos novos.
O inventariador tambem recusa sobrescrita de inventario existente.

Logs reais: `logs\n1-image-derivation.log`, `logs\n1-entry-disassembly.log`,
`logs\n1-switch-disassembly.log`, `logs\n1-360tools-xex-info.log`,
`logs\n1-360tools-imports.log`, `logs\n1-inventory.log`,
`logs\n1-inventory-final.log` e `logs\n1-verification.log`.
A verificacao final compara novamente os 429 hashes, confere fontes/offsets do
JSON, hashes dos scripts e consistencia das contagens. Os tres testes cobrem
limites truncados/negativos, buracos de zeros e tabelas basic malformadas.
Esses testes validam o ferramental de analise, nao o jogo.

A primeira verificacao detectou um limite de citacao uma linha alem do arquivo
`parse_xex_imports.py`; a citacao foi corrigida para 155-208 e o JSON regenerado.
A falha inicial foi preservada em `logs\n1-verification-first.log`.
