./Guion_expert/scripts/claude_api.py:3:Replaces ollama calls with Anthropic Claude API.
./webapp/server.py:399:            'concepto': (APP_CONFIG.get('MODEL_CONCEPTO', 'qwen2.5:7b'), 'prompts/01_concepto.txt'),
./webapp/server.py:400:            'arquitecto': (APP_CONFIG.get('MODEL_ARQUITECTO', 'qwen2.5:14b'), 'prompts/02_arquitecto.txt'),
./webapp/server.py:401:            'escaletista': (APP_CONFIG.get('MODEL_ESCALETISTA', 'qwen2.5:7b'), 'prompts/03_escaletista.txt'),
./webapp/server.py:402:            'dialoguista': (APP_CONFIG.get('MODEL_DIALOGUISTA', 'qwen2.5:14b'), 'prompts/04_dialoguista.txt'),
./webapp/server.py:403:            'localizador': (APP_CONFIG.get('MODEL_LOCALIZADOR', 'qwen2.5:7b'), 'prompts/10_localizador_chile.txt')
./webapp/server.py:469:        model = APP_CONFIG.get('MODEL_ARQUITECTO', 'qwen2.5:14b')
./webapp/server.py:515:        model = APP_CONFIG.get('MODEL_DIRECTOR_FLOW', 'qwen2.5:14b')
./webapp/llm_provider.py:14:    LLM_PROVIDER              claude (default) | ollama
./webapp/llm_provider.py:19:Mantiene una API compatible con el patrón `ollama run model prompt`
./webapp/llm_provider.py:81:    if PROVIDER == "ollama":
./webapp/llm_provider.py:82:        return _ollama_available()
./webapp/llm_provider.py:91:        "model": CLAUDE_MODEL if PROVIDER == "claude" else "ollama",
./webapp/llm_provider.py:110:    elif PROVIDER == "ollama":
./webapp/llm_provider.py:111:        yield from _generate_ollama(model, prompt, stream=stream)
./webapp/llm_provider.py:146:def _ollama_available() -> bool:
./webapp/llm_provider.py:148:        r = subprocess.run(["pgrep", "ollama"], capture_output=True)
./webapp/llm_provider.py:154:def _generate_ollama(model: str, prompt: str, stream: bool = True) -> Iterator[str]:
./webapp/llm_provider.py:155:    cmd = ["ollama", "run", model, prompt]
