# Mesure Lightning / FLUX (16 nov 2026)

RTX 5060 Laptop 8 Go, 512 × 512, ComfyUI lancé par Atelier (`--disable-dynamic-vram --reserve-vram 1 --cache-none`).
Temps = envoi → image enregistrée, une image à la fois, modèles déjà en RAM. Script : `bench.py`.

| Pipeline | Images | Temps moyen | Écart |
|---|---:|---:|---|
| FLUX Schnell, encodeur T5 sur CPU (avant) | 10 | 82 s | référence |
| FLUX Schnell, encodeur T5 sur GPU (`device=default`) | 2 | 53 s | −35 % |
| Qwen 2.1, 28 étapes (avant) | 3 | 101 s | référence |
| Qwen 2.1 + Lightning v2-RL, 4 étapes | 2 | 70 s | −31 % |

Respect du prompt (lecture visuelle) :
- « trois pièces + épée rouge sur table en bois » : FLUX = 7 pièces ; Qwen Lightning = 3 pièces, épée rouge, table → correct.
- « blob rose, deux yeux, une pousse, parapluie bleu tenu » : FLUX tient le parapluie ; Qwen (28 et 4 étapes) le colle sur la bouche.

## Constat
Le calcul de l'image (4 étapes) n'est qu'une petite partie du temps : les journaux montrent que les modèles
(encodeur Qwen3-VL de 8 Go en partie déchargé, transformeur, VAE) sont rechargés vers la carte à chaque image.
`--cache-none` et la mémoire de 8 Go empêchent de les garder. La prochaine piste de vitesse est donc le chargement
(garder l'encodeur en mémoire, encodeur plus léger), pas le nombre d'étapes.

## Après correctif du rechargement (même jour)
ComfyUI sans `--cache-none` (cache RAM par défaut) : les modèles restent chargés entre deux images.
Garder Qwen et FLUX ensemble dépasse 32 Go de RAM (plantage « access violation » constaté au chargement de T5) :
Atelier appelle `/free` de ComfyUI quand la famille de modèle change.

| Pipeline | 1re image (chargement) | 2e | Images suivantes |
|---|---:|---:|---:|
| FLUX Schnell, T5 sur GPU | 64 s | 36 s | **11-17 s** (contre 82 s avant) |
| Qwen Lightning 4 étapes | 38-54 s | 20-41 s | **15-20 s** (contre 101 s avant, 28 étapes) |

## Cohérence avec fiche @Nom (image de référence)
Bean Blob dans 3 scènes (prairie qui court, dort sur un coussin, mange un cookie), Qwen Lightning + image de fiche :
même personnage sur les 3 images (forme, rose, yeux, sourire, pousse à 2 feuilles, pieds) et décor respecté.
Limite : la pose de la référence domine (il ne court pas, il ne dort pas les yeux fermés) ; le cookie est bien tenu.
