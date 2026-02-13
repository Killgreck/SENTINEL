# 🔐 Guía de Credenciales para SENTINEL

Para que el sistema funcione, necesitamos acceso al mercado (Binance) y a los datos históricos (Kaggle/HuggingFace). Sigue estos pasos:

## 1. Binance (Para datos en tiempo real y trading futuro)
*Necesario para el módulo Sentinel HFT y Swing.*

1.  Inicia sesión en tu cuenta de [Binance](https://www.binance.com/).
2.  Ve al ícono de tu perfil -> **Gestión de API**.
3.  Haz clic en **Crear API**.
4.  Etiqueta: `Sentinel_Bot`.
5.  **IMPORTANTE:**
    *   Marca "Enable Reading" (Habilitar lectura).
    *   **NO MARQUES** "Enable Spot & Margin Trading" todavía (por seguridad, primero solo lectura).
    *   **NO MARQUES** "Enable Withdrawals" (NUNCA).
6.  Copia la `API Key` y el `Secret Key`. Guárdalos en un lugar seguro (no me los des todavía, crearemos un archivo `.env` seguro luego).

## 2. Kaggle (Para descargar datasets históricos de Noticias)
*Necesario para descargar los gigabytes de noticias 2021-2024.*

1.  Regístrate en [Kaggle.com](https://www.kaggle.com/).
2.  Ve a tu perfil (arriba derecha) -> **Settings**.
3.  Baja hasta la sección **API**.
4.  Haz clic en **Create New Token**.
5.  Se descargará un archivo `kaggle.json`.
6.  Este archivo contiene tu `username` y `key`. Lo necesitaremos.

## 3. Hugging Face (Para el dataset procesado 2016-2024)
*El "Santo Grial" de los datos limpios.*

1.  Crea cuenta en [Hugging Face](https://huggingface.co/).
2.  Ve a **Settings** -> **Access Tokens**.
3.  Crea un **New Token** con permisos de `Read` (Lectura).
4.  Copia el token (empieza con `hf_...`).

---
**Próximo paso:** Cuando tengas estas claves, crearemos un archivo `.env` en tu servidor para que los scripts puedan usarlas.
