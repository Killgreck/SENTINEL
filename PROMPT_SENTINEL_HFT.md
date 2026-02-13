Actúa como un Ingeniero Principal de Trading de Alta Frecuencia (HFT) y experto en AWS.

**Contexto del Proyecto: SENTINEL**
Estamos construyendo un sistema de trading dual en AWS:
1.  **Sentinel Swing:** Basado en LLMs (Claude 3.5 Sonnet/Opus, Gemini 1.5 Pro) para análisis de sentimiento profundo y estrategia macro.
2.  **Sentinel HFT:** Un módulo de ejecución ultra-rápida.

**Tus Objetivos:**

**1. Arquitectura Sentinel HFT en la Nube:**
*   Explora la viabilidad de HFT real en AWS. No queremos "rápido", queremos "lo más rápido físicamente posible en la nube".
*   Evalúa el uso de instancias **EC2 F1 (FPGAs)**. ¿Podemos programar la lógica de ejecución en hardware para saltarnos el sistema operativo?
*   Redes: Explica cómo usar **Elastic Fabric Adapter (EFA)** y Kernel Bypass para reducir la latencia de red.
*   Lenguajes: Asume C++ o Rust para este módulo, o VHDL/Verilog si sugieres FPGAs.

**2. Estrategia "The Contrarian" (Judo de Mercado):**
*   *Hipótesis:* Las noticias falsas o exageradas están diseñadas para manipular el mercado (Pump & Dump).
*   *Mecánica:* En lugar de filtrar las "Fake News" y no operar, el sistema debe:
    1.  Detectar la noticia viral.
    2.  Usar el LLM para clasificarla como "Alta Probabilidad de Manipulación/Falsedad".
    3.  **Ejecutar una operación INVERSA** a la reacción esperada de la masa. (Si la noticia falsa dice "Bitcoin a $200k", la masa compra, Sentinel HFT debe vender corto inmediatamente aprovechando la liquidez).
*   Diseña el flujo de datos para esta lógica: ¿Cómo conectamos la inferencia del LLM (lenta, ms) con la ejecución HFT (rápida, µs)?

**3. Integración Obligatoria:**
*   **SageMaker Feature Store:** Debe ser la fuente de verdad para los features. No es opcional. Diseña cómo el módulo HFT lee de aquí (o de una caché caliente derivada) con mínima latencia.
*   **Matriz de Experimentos:** Mantén la idea de usar DynamoDB para registrar la eficacia de cada versión del algoritmo.

**Salida Requerida:**
Provee la arquitectura detallada para el módulo HFT y el flujo de la estrategia "Contrarian". Sé brutalmente honesto sobre las limitaciones de latencia en AWS vs. Colocation (Binance/Nasdaq), pero danos la mejor solución *dentro* de AWS. Responde en Markdown.