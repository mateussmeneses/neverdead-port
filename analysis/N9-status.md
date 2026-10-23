# NeverDead N9: Reprodutibilidade de Build, Consolidação de Patches e Suite de QA v2.0

## 1. Contexto e Objetivos do Marco N9

O marco **N9** teve como objetivo consolidar todo o progresso técnico obtido nos marcos N0 a N8, sanando as divergências observadas entre o ambiente de desenvolvimento local e os executores de Integração Contínua (GitHub Actions), além de aprimorar a robustez dos testes automatizados de regressão.

### Principais Diagnósticos Identificados:
1. **Falha no GitHub Actions**: As execuções do CI falharam porque a suite de smoke test tentava validar a presença física do diretório de cache de shaders (`analysis/n7-benchmarks/shader_cache`), o qual é intencionalmente ignorado pelo Git (`.gitignore`) por se tratar de binários gerados em tempo de execução (`.xpso`, `.xsh`).
2. **Classificação Inadequada de Métricas Ausentes**: O arquivo de perfilamento `n7_warm_profile.json` continha `frames_captured = 0` (devido à execução autônoma que para na tela de título/prompt interativo da engine Asura aguardando o comando Start/A). A suite anterior tratava tempos de quadro nulos como `PASS`, em vez de classificar a métrica como inconclusiva por ausência de amostras interativas.
3. **Invocação Quebrada do Modo `--run-live`**: A chamada interna em `qa_smoke_test.py` passava apenas 2 argumentos para `profile_n7.run_benchmark`, que exige 7 parâmetros posicionais.
4. **Isolamento de Clones Limpos**: Um clone limpo do repositório não contém `refs/` (vários gigabytes de ferramentas upstream) nem `src/generated/` (código gerado a partir do dump legal proprietário). O CI precisa executar de forma autônoma e verde sem exigir ativos proprietários.
5. **Portabilidade do Script de Symlinks**: `Invoke-BuildWithSymlinks.ps1` possuía caminhos absolutos hardcoded para `C:\projetos\neverdead`, que poderiam falhar em outras pastas ou sistemas.

---

## 2. Ações Implementadas e Soluções de Engenharia

### 2.1. Arquitetura de Diagnóstico de 4 Estados da Suite QA (`qa_smoke_test.py`)
A ferramenta de testes de regressão foi reestruturada para suportar um modelo formal de quatro estados:
- **`[PASS]`**: Evidência positiva auditada satisfaz integralmente o critério de qualidade (ex.: zero traps fatais, zero erros D3D12, consumo de RAM dentro do teto).
- **`[FAIL]`**: Regressão real ou violação de invariante detectada (ex.: trap fatal > 0, erro de renderização Direct3D 12, estouro de teto de memória).
- **`[SKIP]`**: Teste ou verificação omitida por desenho de arquitetura em ambientes sem dependências instaladas (ex.: ausência de diretório de shader cache no runner de CI, ausência de dump do jogo no ambiente do executor).
- **`[INCONCLUSIVE]`**: Métrica capturada de forma indeterminada ou com dados incompletos (ex.: `frames_captured == 0` com processo retido na barreira de título interativo). Nenhuma métrica ausente é aceita como zero válido.

### 2.2. Separação de Testes Independentes e Dependentes de Ativos
A validação de qualidade foi categorizada em camadas bem delimitadas:
- **Camada 1 — Independente de Jogo/GPU (Executável em Qualquer Runner/CI)**:
  - Higiene estrita de repositório (varredura recursiva garantindo 0 binários `.xex`, `.zar`, `.iso`, `.asrBE` no Git);
  - Validação de integridade de telemetria dos marcos de benchmark (`n7_cold_profile.json`, `n7_warm_profile.json`, `n7_benchmark_comparison.csv`);
  - Verificação de persistência de shader cache (aprovado quando presente localmente; graciosamente pulado com `[SKIP]` em runners limpos);
  - Guarda de execução de runner live (detecta ausência do dump e pula de forma limpa com código de saída 0).
- **Camada 2 — Dependente de Ativos e Executável (Ambiente do Desenvolvedor)**:
  - `--run-live`: Lança o executável compilado com todos os CVars necessários (`--gpu_allow_invalid_fetch_constants=true`, `--mnk_mode=true`), coleta memória via `GetProcessMemoryInfo` da API Win32, monitora o log em tempo real e analisa os resultados em 4 estados.

### 2.3. Unificação e Portabilidade dos Patches do ReXGlue SDK
Foi gerado o patch formal [`analysis/patches/rexglue_sdk_neverdead.patch`](file:///C:/projetos/neverdead/analysis/patches/rexglue_sdk_neverdead.patch), contendo:
1. Suporte a `XFileXctdCompressionInformation` em `xboxkrnl_io_info.cpp` e `file.h`;
2. Diagnóstico aprimorado de traps com exibição de `LR` e `SP` em `function_dispatcher.cpp`;
3. Inicialização segura e lazy do arquivo CSV de contadores de performance em `counter.cpp`;
4. Compilação irrestrita de `REXGLUE_ENABLE_PERF_COUNTERS` no CMake;
5. Correção de literais brutos de escape no teste unitário `output_stamp_test.cpp` da SDK upstream;
6. Testes unitários dedicados em `file_info_test.cpp` e `sync_primitives_test.cpp`.

Todos os **214 testes unitários C++** do ReXGlue SDK foram executados e aprovados:
```text
test cases: 218 | 214 passed | 4 skipped
assertions: 893 | 893 passed
```

### 2.4. Portabilidade do `Invoke-BuildWithSymlinks.ps1`
O script de materialização temporária de hardlinks para o `libmspack` foi parametrizado para utilizar caminhos relativos derivados de `$PSScriptRoot`, funcionando de forma determinística em qualquer caminho de instalação.

### 2.5. Correção do GitHub Actions Workflow
O arquivo [`.github/workflows/build.yml`](file:///C:/projetos/neverdead/.github/workflows/build.yml) foi atualizado para:
- Executar a checagem de higiene de ativos;
- Executar a suite de regressão com tolerância a diretórios de cache gitignorados via status `[SKIP]`;
- Validar a guarda do modo `--run-live` garantindo que o runner de CI não falhe por falta de ativos proprietários.

---

## 3. Matriz de Verificação Local dos Testes

| Teste Executado | Comando Real | Resultado Obtido | Status |
| :--- | :--- | :--- | :---: |
| **Higiene de Repositório** | `python analysis/qa_smoke_test.py --verify-recent` | 0 arquivos proprietários detectados no Git. | **PASS** |
| **Invariantes de Log & Trap** | `python analysis/qa_smoke_test.py --verify-recent` | 0 traps fatais observados (Cold e Warm). | **PASS** |
| **Invariantes D3D12 & Texturas**| `python analysis/qa_smoke_test.py --verify-recent` | 0 erros D3D12, 0 warnings de textura. | **PASS** |
| **Limites de Memória (RSS/Commit)**| `python analysis/qa_smoke_test.py --verify-recent`| RSS de 552–561 MB (teto 1024 MB), Commit de 1.35 GB (teto 2048 MB). | **PASS** |
| **Auditoria de Shader Cache** | `python analysis/qa_smoke_test.py --verify-recent` | 2 binários válidos detectados localmente; classificado como `SKIP` caso ausente no CI. | **PASS / SKIP** |
| **Métricas de Frametime** | `python analysis/qa_smoke_test.py --verify-recent` | `frames_captured = 0` classificado corretamente como inconclusivo. | **INCONCLUSIVE** |
| **Execução Live do Port (5s)** | `python analysis/qa_smoke_test.py --run-live --seconds 5` | Processo executou 5s, 0 crashes, 0 traps, RSS de 466 MB, Commit de 1.01 GB. | **PASS** |
| **Testes Unitários C++ da SDK** | `refs/core/rexglue-sdk/out/win-amd64/Release/unit_tests.exe` | 214 testes aprovados, 4 pulados upstream, 0 falhas. | **PASS** |

---

## 4. Próximos Passos Recomendados

1. **Validação do CI no GitHub**: Enviar as correções de N9 para o remoto (`git push origin main`) mediante autorização do usuário e acompanhar o status verde da pipeline no GitHub Actions.
2. **Inlining de Despacho de Blocos PPC (Marco P1 do Roadmap)**: Reduzir a sobrecarga de chamadas indiretas nas funções recompiler-generated para melhorar o framerate em combates intensos.
3. **Mapeamento de Instruções Vetoriais AVX2 para VMX128 (Marco P2 do Roadmap)**: Otimizar o subsistema de física de desmembramento de Bryce e partículas.
