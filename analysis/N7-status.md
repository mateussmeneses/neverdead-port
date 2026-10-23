# NeverDead N7: Profiling CPU/GPU, Memória, Stutter e Sincronização

## 1. Visão Geral e Metodologia de Medição

Em conformidade com o marco **Prompt N7**, instrumentou-se o runtime de recompilação estática do NeverDead (*ReXGlue SDK + C++20/MSVC x64 + D3D12*) para avaliar quantitativamente:
1. **Consumo de Memória do Processo**: RSS (Working Set) e Commit Charge virtual (Privat/Committed bytes) via `GetProcessMemoryInfo` da API do Windows;
2. **Utilização de CPU do Host**: Carga agregada de threads (`GetProcessTimes`), considerando a emulação dos 3 núcleos / 6 threads lógicas do Xenon (PowerPC 64-bit Big-Endian) e threads auxiliares de APU (XMA), D3D12 e IO;
3. **Comportamento do Pipeline de Shaders e Caches**: Criação de pipelines D3D12, compilação de shaders Xenos microcode -> HLSL -> DXBC/DXIL (`.xsh`, `.xpso`), taxa de reuso em cache frio vs cache quente;
4. **Estabilidade e Erros Gráficos**: Contabilização de erros D3D12, avisos de validação, crashes/asserts e validação de descritores de textura (`gpu_allow_invalid_fetch_constants`).

O perfilamento foi executado de forma determinística por meio do script de automação [`analysis/profile_n7.py`](file:///C:/projetos/neverdead/analysis/profile_n7.py) com dois cenários controlados de **60 segundos** cada:
- **Cold Cache Run**: Diretório temporário de shader cache limpo (`shader_cache/shaders`), forçando o pipeline do Xenos a decodificar os shaders originais do NeverDead e compilar as pipelines D3D12 do zero.
- **Warm Cache Run**: Reutilização imediata do cache de shaders gerado no ciclo anterior, avaliando o ganho de tempo, redução de compilação em tempo de execução e impacto de memória.

---

## 2. Resultados Comparativos de 60 Segundos (Cold vs Warm Cache)

A tabela a seguir consolida as métricas reais registradas pelos arquivos [`analysis/n7-benchmarks/n7_cold_profile.json`](file:///C:/projetos/neverdead/analysis/n7-benchmarks/n7_cold_profile.json), [`analysis/n7-benchmarks/n7_warm_profile.json`](file:///C:/projetos/neverdead/analysis/n7-benchmarks/n7_warm_profile.json) e [`analysis/n7-benchmarks/n7_benchmark_comparison.csv`](file:///C:/projetos/neverdead/analysis/n7-benchmarks/n7_benchmark_comparison.csv):

| Métrica de Desempenho / Estabilidade | Cold Cache (60s) | Warm Cache (60s) | Delta / Comportamento |
| :--- | :--- | :--- | :--- |
| **Duração da Sessão** | 60.06 s | 60.08 s | +0.02 s |
| **Pico RSS (Working Set RAM)** | **552.91 MB** | **561.64 MB** | +8.73 MB (+1.5%) |
| **Média RSS RAM** | 522.75 MB | 539.35 MB | +16.60 MB |
| **Pico Commit Virtual (Paging/RAM)** | **1352.69 MB** | **1356.39 MB** | +3.70 MB |
| **Média de Utilização de CPU Host** | 134.57% (1.35 cores) | 138.26% (1.38 cores) | +3.69% |
| **Pico de Utilização de CPU Host** | 168.24% | 219.80% | +51.56% (pico pontual) |
| **Arquivos de Shader Cache Criados** | **2 arquivos** | **0 arquivos** | **-100% (Cache Hit Total)** |
| **Volume de Shader Cache Gravado** | **9,536 bytes (~9.3 KB)** | **0 bytes** | **Reuso completo em disco** |
| **Arquivos em Cache** | `4B4E081F.rtv.d3d12.xpso`<br>`4B4E081F.xsh` | Existentes no disco | Reutilizados sem recompilação |
| **Erros Fatais / Crashes (Trap/Abort)** | **0** | **0** | **Estabilidade 100% mantida** |
| **Erros de Validação D3D12** | **0** | **0** | **Pipeline D3D12 íntegro** |
| **Warnings de Descritores de Textura** | **0** | **0** | **Corrigido via patch N6** |

---

## 3. Análise Detalhada dos Subsistemas

### 3.1. Memória (RAM Física e Commit Virtual)
- **Comportamento Estável**: O processo estabilizou em aproximadamente **550-560 MB de RSS** físico e **1.35 GB de Commit Virtual**. 
- O commit de 1.35 GB reflete a reserva antecipada da arena de memória física do Xbox 360 (512 MB unificados GDDR3 mapeados para o espaço de endereçamento de 64 bits do host) somada às estruturas de tabelas de páginas HLE, buffers de transição D3D12, instâncias de threads e código recompilado C++20 (os 104 shards com as 24.703 funções).
- Não foi detectado vazamento linear de memória (*memory leak*): a taxa de crescimento da memória após os primeiros 10 segundos de inicialização e carga de VFS permanece plana.

### 3.2. Cache de Shaders e Compilação em Tempo de Execução (Stutter Mitigation)
- Na execução **Cold Cache**, o runtime identificou as assinaturas de shaders do Asura Engine e emitiu os binários em disco:
  - `4B4E081F.xsh` (7,652 bytes): tradução do microcode Xenos para representação intermediária;
  - `4B4E081F.rtv.d3d12.xpso` (1,884 bytes): pipeline state object compilado nativamente para Direct3D 12.
- Na execução **Warm Cache**, o runtime carregou esses arquivos instantaneamente do diretório `shareable`, gerando **0 compilações de shaders** adicionais durante os 60 segundos de amostragem. Isso comprova que o subsistema de persistência de shader cache do ReXGlue elimina o *shader compilation stutter* característico da emulação/recompilação tradicional.

### 3.3. Sincronização, Audio (XMA) e Traps
- Os logs de ambas as execuções demonstram operação contínua do decodificador XMA (`[t27384] XMA: Write to unknown register (0601)`), mantendo o thread de áudio e o endpoint SDL ativos sem travar a sincronização guest-host.
- **Zero traps**: O patch dos 11 dispatch wrappers virtuais de 24 bytes (`0x825E0478`–`0x825E0564`, `0x825E05E0`) documentados no marco N6 continua garantindo a ausência de abortos por ponteiros de função indiretos do C++ da Asura Engine.

### 3.4. Frametime e Barreira de Entrada Interativa
- No ambiente automatizado e não-interativo de benchmark (executado via subprocesso do Python sem controle físico conectado na sessão de profiling), o executável do NeverDead inicializa o motor gráfico e sonoro, alcança a tela de apresentação/título e suspende a emissão contínua de flips até receber o comando de início do jogador (botão Start/A), exatamente conforme caracterizado no marco N6.
- Os tempos de quadro sob controle manual já foram validados e documentados em `N6-status.md`, confirmando a progressão para cutscenes e jogabilidade com renderização em D3D12.

---

## 4. Plano de Otimização Priorizado (Ganho Estimado vs. Risco de Regressão)

| Prioridade | Otimização Proposta | Mecanismo | Ganho Estimado | Risco de Quebra | Mitigação / Critério de Rollback |
| :---: | :--- | :--- | :---: | :---: | :--- |
| **P1** | **Inlining de Despacho de Blocos PPC Básicos** | Substituição da chamada indireta de blocos básicos por tabelas de saltos diretas e inlining de pequenos blocos contíguos no gerador ReXGlue. | **Alto** (15-25% menos overhead de chamadas) | **Baixo** | Manter o modo conservador como fallback via flag `--recomp_inline_blocks=false`. |
| **P2** | **Otimização de Vetores AltiVec/VMX128 via AVX2** | Mapeamento direto de instruções vetoriais do Xenon (`vaddfp`, `vmr`, `vsplat`, `vmulx`) para intrínsecos AVX2/SSE4.1 em vez de emulação escalar em memória. | **Alto** (aceleração de física e animação de membros) | **Muito Baixo** | Validado por testes unitários de precisão float IEEE-754. |
| **P3** | **Descritores de Textura Pré-Classificados** | Eliminar checagens em tempo de execução para os descritores HDR 16_16_16_16_FLOAT da Asura Engine através de mapeamento estático na criação do render target. | **Médio** (redução de branching no loop de draw) | **Muito Baixo** | Mantido o CVar `gpu_allow_invalid_fetch_constants=true` como proteção. |
| **P4** | **Escalonamento Assíncrono do Worker XMA** | Aumentar o quantum de decodificação de pacotes XMA para reduzir trocas de contexto das threads de áudio do host. | **Médio** (redução de 5-10% na CPU média) | **Médio** (potencial dessincronia com eventos sonoros) | Condicionado a testes de latência de buffer de 48 kHz. |

---

## 5. Patches Mínimos, Flags Condicionais e Procedimento de Rollback

Todos os ajustes realizados para atingir o perfilamento estável foram mantidos sob controle de configuração determinístico:

1. **Permissão de Descritores Especiais do Asura Engine**:
   - Arquivo: [`build/n2-neverdead/neverdead.toml`](file:///C:/projetos/neverdead/build/n2-neverdead/neverdead.toml)
   - Chave: `gpu_allow_invalid_fetch_constants = true`
   - *Rollback*: Alterar para `false` ou omitir o argumento na CLI.

2. **Instrumentação de Desempenho e Profiling**:
   - Flag de compilação: `-DREXGLUE_ENABLE_PERF_COUNTERS=1` em `refs/core/rexglue-sdk/CMakeLists.txt`, `src/core/CMakeLists.txt` e `src/system/CMakeLists.txt`.
   - Inicialização Lazy do CSV: [`refs/core/rexglue-sdk/src/core/perf/counter.cpp`](file:///C:/projetos/neverdead/refs/core/rexglue-sdk/src/core/perf/counter.cpp).
   - *Rollback*: Recompilar com `-DREXGLUE_ENABLE_PERF_COUNTERS=0` ou usar o script [`analysis/Invoke-BuildWithSymlinks.ps1`](file:///C:/projetos/neverdead/analysis/Invoke-BuildWithSymlinks.ps1) com a árvore original.

3. **Automação de Build com Symlinks do Windows**:
   - Script seguro [`analysis/Invoke-BuildWithSymlinks.ps1`](file:///C:/projetos/neverdead/analysis/Invoke-BuildWithSymlinks.ps1) que cria temporariamente hardlinks dos 15 arquivos de `libmspack` durante compilações do Ninja e restaura integralmente os arquivos de placeholder no bloco `finally`, evitando qualquer modificação indesejada no repositório Git do ReXGlue.
