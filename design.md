# Design.md - Dirección visual del proyecto CIAR

## Propósito de este archivo

Este documento es la guía visual que debe leer cualquier modelo antes de crear o modificar la interfaz de CIAR. El proyecto es un asistente de la Universidad de Lima que consulta información académica y de empleabilidad, por lo que debe comunicar rigor, confianza, claridad, innovación y cercanía institucional.

La fuente de verdad de la marca es `LINEAMIENTOS_DE_MARCA.pdf`, el Brand Book de la Universidad de Lima elaborado por la Dirección Universitaria de Comunicación. El PDF contiene el detalle completo del logotipo, arquitectura de marca, colores, tipografías, usos correctos e incorrectos, sistema gráfico, formatos y flujo de validación. Este archivo traduce sus decisiones principales a reglas concretas para este producto; si existe una duda o contradicción, prevalece el PDF original.

## Instrucción principal para el modelo

Construye una interfaz editorial e institucional, moderna y orientada a datos. Debe verse como una herramienta académica confiable de la Universidad de Lima, no como una plantilla genérica de SaaS ni como una aplicación experimental.

Prioriza, en este orden:

1. Identidad oficial de la Universidad de Lima.
2. Legibilidad y accesibilidad.
3. Jerarquía clara de información.
4. Consistencia entre chat, dashboard, normalizador y estados de la aplicación.
5. Uso expresivo, pero controlado, de color y recursos gráficos.

No inventes logotipos, submarcas, colores o recursos visuales que no estén respaldados por el manual de marca.

## Personalidad visual

La experiencia debe sentirse:

- Institucional, seria y con autoridad académica.
- Contemporánea, limpia y digital.
- Inteligente y precisa, especialmente en tablas, respuestas y visualizaciones.
- Humana y útil, sin caer en un tono infantil o excesivamente corporativo.
- Editorial: titulares con presencia, buen uso del espacio en blanco, líneas finas y composición ordenada.

La referencia visual es una combinación de diseño editorial universitario, sistema de información y producto digital premium. La composición puede ser asimétrica y usar bloques de color, pero siempre debe mantener una retícula clara y una lectura sencilla.

## Identidad de marca

### Logotipo

- Usa siempre el asset oficial de la Universidad de Lima. En el repositorio actual se debe reutilizar `frontend/public/logo-ulima.png` cuando sea la versión adecuada.
- La versión horizontal completa es la opción principal para encabezados, navegación y espacios institucionales.
- La versión vertical se reserva para casos excepcionales en los que el isotipo necesite mayor jerarquía visual.
- El isotipo puede usarse solo en espacios compactos, como el rail colapsado o un estado de carga, siempre que no se convierta en un logotipo nuevo.
- Si se muestra `Agente CIAR`, debe ser una etiqueta independiente de la marca oficial. No debe reconstruirse un lockup juntando el isotipo con el nombre del proyecto.
- Mantén un área libre alrededor del logo. Ningún texto, botón, imagen, borde o componente debe tocarlo o invadir su zona de protección.
- Respeta como referencia los tamaños mínimos del manual: isotipo de 30 px en digital, logo horizontal de 120 px y logo vertical de 120 px. Nunca reduzcas el logo hasta perder legibilidad.

### Prohibiciones del logotipo

Nunca:

- Lo reconstruyas con una tipografía.
- Cambies la proporción, el orden o el tamaño relativo de sus partes.
- Lo estires, comprimas, gires, inclines, recortes o distorsiones.
- Cambies sus colores por azul, morado, verde u otros colores arbitrarios.
- Le agregues sombras, brillos, degradados o efectos de volumen.
- Coloques texto debajo del logotipo.
- Uses el isotipo junto al nombre de una facultad, carrera, área o dependencia como si fuera una nueva marca.
- Uses un dibujo generado por IA como sustituto del asset oficial.

## Paleta cromática

### Colores institucionales

El naranja y el negro son la base de la identidad. Deben conservar prioridad visual sobre los colores secundarios.

| Token sugerido | Color | Referencia de marca | Uso en CIAR |
| --- | --- | --- | --- |
| `brand-orange` | `#FF5117` | Pantone 165 C / 165 U; RGB 255, 81, 23; CMYK 0, 70, 100, 0 | CTA principal, estados activos, acentos, titulares destacados, identidad |
| `brand-black` | `#000000` | Pantone Black C / Black U; RGB 0, 0, 0; CMYK 0, 0, 0, 100 | Texto de máxima jerarquía, estructura, fondos oscuros y elementos de autoridad |
| `brand-gray` | `#97999B` | Pantone Cool Gray 7 C / 7 U; RGB 151, 153, 155; CMYK 20, 14, 12, 40 | Soporte visual, metadatos, estados secundarios y diagramación |

Para superficies digitales se pueden usar blanco y neutrales muy claros derivados de la interfaz, como `#FFFFFF`, `#FAFAFA`, `#F1F1F3` y `#E4E4E7`. Estos tonos deben servir para estructura y legibilidad, no competir con el naranja institucional.

### Colores secundarios

Los secundarios complementan la identidad. Se usan para comunicar contexto, categoría o emoción, no para reemplazar el naranja institucional. No asignes permanentemente un color a una carrera, dependencia o facultad.

| Token sugerido | Color | Referencia de marca | Significado recomendado en CIAR |
| --- | --- | --- | --- |
| `secondary-turquoise` | `#00C5D6` | Pantone 3115 C; RGB 0, 198, 215; CMYK 69, 0, 29, 0 | Innovación, tecnología, transformación digital y datos |
| `secondary-amber` | `#FFA000` | Pantone 137 C; RGB 255, 161, 0; CMYK 0, 38, 95, 0 | Dinamismo, juventud, acción y convocatorias |
| `secondary-green` | `#00C78B` | Pantone 3395 C; RGB 0, 199, 139; CMYK 74, 0, 52, 0 | Crecimiento, bienestar, sostenibilidad y empleabilidad |
| `secondary-gray` | `#C3C8C8` | Pantone 428 C; RGB 195, 200, 200; CMYK 12, 6, 5, 12 | Academia, racionalidad, equilibrio y soporte |
| `secondary-beige` | `#DAC9B5` | Pantone 482 C; RGB 218, 201, 181; CMYK 2, 13, 18, 6 | Cercanía, tradición, humanidad y prestigio |
| `secondary-pink` | `#F3BBCE` | Pantone 1895 C; RGB 243, 187, 206; CMYK 0, 28, 2, 0 | Comunidad, empatía, diversidad y bienestar |

Reglas de uso:

- Una pantalla debe tener una jerarquía cromática evidente: institucional primero, secundarios después.
- Usa un secundario cuando ayude a clasificar o explicar la información. No uses todos los colores en cada vista.
- Los secundarios pueden combinarse y formar degradados suaves, pero solo entre colores aprobados y con una intención clara.
- Los gráficos deben conservar suficiente contraste y no depender únicamente del color para comunicar una diferencia.
- No uses degradados multicolor, neones, transparencias decorativas ni fondos saturados que opaquen el contenido.
- El azul de herramientas de accesibilidad o de estados funcionales solo puede aparecer cuando sea necesario para accesibilidad o semántica del sistema; no debe convertirse en parte del lenguaje visual de marca.

## Tipografía

Las fuentes oficiales del manual están disponibles en Google Fonts: `Roboto` y `Lusitana`.

### Roboto

Es la familia principal para la interfaz, navegación, formularios, tablas, métricas y contenido operativo.

- `Roboto Light`: encabezados o información relevante en mayúsculas. No usarla como cuerpo pequeño.
- `Roboto Regular`: cuerpo de texto, descripciones, ayuda y contenido general.
- `Roboto Medium`: subtítulos, etiquetas importantes y títulos secundarios.
- `Roboto Bold` y `Roboto Black`: títulos, CTAs, cifras clave y énfasis de alta jerarquía.

### Lusitana

Es la familia editorial y debe usarse con moderación para aportar carácter académico y humano.

- `Lusitana Regular`: cuerpo editorial, subtítulos o textos narrativos que necesiten una voz más cálida.
- `Lusitana Bold`: títulos editoriales, citas, mensajes de bienvenida o énfasis dentro de una pieza gráfica.
- En subtítulos destacados puede usarse en mayúsculas; en cuerpo de texto debe preferirse la escritura normal en minúsculas.

Reglas prácticas:

- Usa Roboto para casi toda la interacción de CIAR. Reserva Lusitana para una capa editorial concreta, no para todos los componentes.
- No mezcles más de dos familias tipográficas dentro de un mismo componente.
- No introduzcas una tipografía display, manuscrita o futurista para llamar la atención.
- `IBM Plex Mono` puede mantenerse solo para timestamps, identificadores técnicos, Cypher, schema o datos claramente monoespaciados. No debe usarse como tipografía principal de marca.
- Mantén una jerarquía visible entre título, subtítulo, cuerpo, metadato y acción. El tamaño y el peso deben hacer evidente qué debe leerse primero.

## Composición y layout

- Usa una retícula consistente, márgenes generosos y alineaciones repetibles.
- Prefiere superficies planas blancas o neutrales, separadas por líneas finas y cambios sutiles de tono.
- Usa bloques naranjas o negros para crear foco y jerarquía, no para llenar toda la pantalla sin propósito.
- Mantén los textos alineados a la izquierda salvo que exista una razón editorial clara para centrarlos.
- Deja espacio alrededor de titulares, logos, tablas y acciones. El espacio en blanco es parte de la identidad.
- Usa radios moderados en el producto digital, aproximadamente entre 10 y 16 px para controles y tarjetas. No conviertas cada elemento en una píldora.
- Las sombras deben ser suaves y discretas. Evita paneles flotantes con sombras grandes, glassmorphism, blur decorativo y tarjetas anidadas sin necesidad.
- Una pantalla puede tener un bloque oscuro con texto blanco y acentos naranja, especialmente para portadas, estados destacados o visualizaciones, siempre que el contraste sea correcto.

## Cómo debe verse cada parte de CIAR

### Shell de la aplicación

- La aplicación ocupa toda la ventana y mantiene una estructura estable: barra lateral, barra superior y área principal.
- La barra lateral puede usar un neutral claro como `#F1F1F3`; la zona de trabajo debe usar blanco o `#FAFAFA`.
- El logo oficial debe tener presencia sin competir con el título de la conversación.
- `Agente CIAR` y `Universidad de Lima` se presentan como información de producto separada del logo oficial.
- El estado activo se puede indicar con una barra lateral naranja de pocos píxeles, un borde sutil o una superficie blanca; no con un bloque naranja pesado en toda la navegación.
- La navegación debe sentirse editorial y ordenada, no como un panel administrativo saturado.

### Pantalla de bienvenida

- Debe abrir con un titular claro, fuerte y breve.
- Resalta palabras clave como `formación`, `empleo`, `carreras` o `empleabilidad` con naranja institucional.
- La explicación debe ser corta y orientada a la acción: el usuario debe entender que puede preguntar en español y recibir respuestas basadas en el grafo.
- Las sugerencias de preguntas pueden organizarse como tarjetas blancas con borde fino, etiqueta de categoría y un pequeño acento secundario.
- No llenes la pantalla con ilustraciones genéricas. La jerarquía tipográfica y el contenido son el foco.

### Chat y respuestas

- El mensaje del usuario puede usar una superficie naranja institucional; valida el contraste del texto. Para texto pequeño, usa negro si el blanco no alcanza el nivel de contraste requerido.
- La respuesta del agente debe priorizar texto legible sobre una tarjeta decorativa. Usa negro para el contenido y gris para metadatos.
- Tablas, listas y bloques de evidencia deben parecer partes de una herramienta académica, con encabezados claros, líneas finas y números alineados.
- Los resultados importantes pueden usar naranja para enlaces, indicadores o valores destacados, sin colorear párrafos completos.
- El estado de carga debe ser sobrio: isotipo oficial o indicador simple, texto breve y movimiento discreto. Respeta `prefers-reduced-motion`.
- Los mensajes de error, advertencia y validación deben ser claros y no depender solo de rojo, amarillo o azul; acompáñalos con texto e iconos.

### Dashboard y visualizaciones

- El dashboard debe sentirse como una sala de análisis académica: limpio, modular, legible y con alta densidad informativa controlada.
- Usa negro y naranja para la jerarquía principal de KPIs, títulos y acciones.
- Usa colores secundarios para diferenciar series o dimensiones solo cuando exista significado. La leyenda debe explicar cada color.
- Prefiere gráficos simples, etiquetas visibles y números con formato consistente antes que efectos 3D o decorativos.
- Las tablas deben ser cómodas de leer, con filas aireadas, encabezados fuertes y estados de hover discretos.
- No uses colores fijos para representar una facultad, una carrera o una dependencia si eso fragmenta la marca.

### Normalizador y formularios

- La interfaz debe comunicar precisión y control del proceso.
- Presenta los pasos de validación de forma lineal, con una acción principal naranja y estados secundarios sobrios.
- Los archivos, nombres técnicos y resultados de normalización pueden usar `IBM Plex Mono` como apoyo funcional.
- Los estados de éxito, advertencia y error deben incluir una descripción accionable y mantener la jerarquía institucional.

## Iconos, imágenes y recursos gráficos

- Usa una sola familia de iconos lineales, con peso y tamaño consistentes. Los iconos de Lucide ya usados en el frontend son adecuados para acciones de interfaz.
- Los iconos deben apoyar la lectura y nunca reemplazar una etiqueta importante.
- No uses el isotipo como icono universal de todos los botones o funciones.
- Si se usan fotografías, deben mostrar aprendizaje, estudiantes, docentes, investigación, colaboración o desarrollo profesional de manera natural y contemporánea.
- Evita fotografías de stock obvias, poses artificiales, fondos excesivamente corporativos y bancos de imágenes sin relación con la vida universitaria.
- Las fotografías pueden convivir con bloques naranja, negro o secundarios aprobados. Los overlays oscuros deben mejorar la legibilidad, no convertir la imagen en un filtro genérico.
- Los recursos geométricos pueden inspirarse en la retícula de la marca, pero no deben redibujar ni deformar el isotipo oficial.

## Responsive y formatos

En el producto web, la composición debe adaptarse desde 320 px sin perder logo, jerarquía ni acciones principales. La barra lateral puede convertirse en menú móvil; el contenido, tablas y gráficos deben tener una estrategia explícita de desplazamiento o reflujo.

Si se generan piezas promocionales o plantillas para redes, usar las medidas del manual:

| Uso | Medida |
| --- | --- |
| Post vertical | 1080 x 1350 px |
| Story | 1080 x 1920 px |
| Publicación cuadrada | 1200 x 1200 px |
| Publicación horizontal | 1200 x 627 px |
| Publicación horizontal para X | 1600 x 900 px |

En piezas sociales se deben respetar las áreas seguras para logo, isotipo, tagline, cobranding y contenido. En formato story también se deben dejar libres las zonas que cubren la interfaz de la plataforma.

## Accesibilidad

La marca nunca debe imponerse sobre la accesibilidad.

- Verifica contraste de texto, botones, bordes, estados y gráficos.
- No dependas solo del color para diferenciar series, estados o errores.
- Mantén navegación por teclado, focus visible, labels, alt text y semántica HTML.
- Conserva el panel de accesibilidad existente y sus funciones.
- Los colores funcionales de accesibilidad pueden ser distintos de la paleta Ulima cuando sea necesario para cumplir su propósito; deben permanecer aislados del lenguaje de marca principal.
- Respeta el tamaño de texto configurado por el usuario y `prefers-reduced-motion`.
- No ocultes información importante al activar modos de lectura, alto contraste o reducción de movimiento.

## Reglas para implementar en este repositorio

- Lee este archivo antes de tocar `frontend/src`, `frontend/app` o los archivos de configuración visual.
- Reutiliza los tokens existentes de `frontend/tailwind.config.js`: `ulima`, `institucional`, `secundario`, `ink`, `paper`, `fondo`, `line`, `muted`, `editorial` y `mono`.
- Reutiliza `frontend/public/logo-ulima.png`; no generes un reemplazo si el asset existente cumple la necesidad.
- Mantén `Roboto` y `Lusitana` como las familias de marca. No agregues fuentes nuevas para resolver una decisión estética puntual.
- Usa clases y helpers existentes antes de crear nuevos patrones.
- No cambies la lógica del agente, el flujo de conversaciones, las consultas a Neo4j ni la accesibilidad para hacer un ajuste visual.
- Si una nueva vista necesita un color, primero intenta resolverla con los tokens institucionales, secundarios o neutrales existentes.
- Si necesitas una expansión de marca, un nuevo lockup o una pieza que no encaje en estas reglas, detente y solicita validación de la Dirección Universitaria de Comunicación.

## Lista de verificación antes de entregar una vista

- [ ] El logo es el asset oficial, conserva sus proporciones y tiene espacio suficiente.
- [ ] El naranja `#FF5117` y el negro mantienen la prioridad visual.
- [ ] Los colores secundarios tienen una función clara y no dominan la identidad.
- [ ] La tipografía usa Roboto para la interfaz y Lusitana solo donde aporta carácter editorial.
- [ ] La jerarquía de títulos, cuerpo, metadatos y acciones se entiende sin esfuerzo.
- [ ] La pantalla no parece una plantilla genérica, un dashboard saturado o una composición con efectos decorativos innecesarios.
- [ ] El contenido mantiene contraste, foco de teclado, responsive y soporte para reducción de movimiento.
- [ ] Los gráficos y tablas explican la información sin depender únicamente del color.
- [ ] No se modificó la lógica del producto para lograr el cambio visual.

## Resumen operativo

Cuando tengas que decidir cómo se ve una nueva pantalla, imagina una publicación editorial de la Universidad de Lima convertida en una herramienta digital: fondo claro, tipografía fuerte, naranja institucional como señal de acción, negro para autoridad, grises para estructura, secundarios para significado y mucho espacio para que los datos respiren. La solución debe ser clara, sobria, académica y reconociblemente Ulima.
