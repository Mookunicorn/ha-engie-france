# Engie France – Prix de l'électricité pour Home Assistant

Intégration personnalisée (HACS) qui lit **tes prix** dans l'espace client Engie
(page « Historique des prix de l'électricité ») et les expose en capteurs :
prix du kWh, abonnement, détail par plage (HP/HC, saison haute/basse).
Le site n'est interrogé **une fois par jour** (avec un cache local pour éviter un 2ᵉ appel après un redémarrage).

> Projet non officiel, sans lien avec Engie. Il utilise une API interne non documentée du site :
> elle peut changer sans préavis. À utiliser pour ton propre compte uniquement.

## Installation (HACS)

1. HACS → ⋮ → **Dépôts personnalisés** → colle l'URL de ce dépôt, catégorie **Intégration**.
2. Installe **Engie France – Prix électricité**, redémarre Home Assistant.
3. Paramètres → Appareils et services → **Ajouter une intégration** → *Engie France*.

## Authentification (v0.1 : cookie de session)

Pour l'instant l'intégration utilise le **cookie de ta session navigateur** (la connexion par
email / mot de passe / code SMS ou mail viendra dans une version suivante).

1. Connecte-toi sur <https://particuliers.engie.fr> et ouvre la page
   `espace-client/consommations/historique-prix-electricite.html`.
2. Ouvre les outils de développement (F12) → onglet **Réseau** → recharge la page.
3. Clique sur la requête `historiquePrix?origin=maconso` → **En-têtes de requête** → copie la valeur de `cookie`.
4. Colle-la dans le formulaire de l'intégration.

Quand la session expire, Home Assistant affiche une demande de **réauthentification** : colle un cookie récent.
Le cookie est stocké dans la configuration de Home Assistant (non chiffrée) : traite-le comme un mot de passe.

## Capteurs

| Capteur | Description |
|---|---|
| Prix du kWh (estimé, saison en cours) | **À utiliser dans le tableau Énergie** (`EUR/kWh`). Fourniture + obligations + acheminement pondéré HP/HC pour la saison en cours (haute : nov.–mars). |
| Prix du kWh (moyenne indicative Engie) | La moyenne annuelle affichée par Engie. |
| Prix du kWh – fourniture / obligations | Composantes fixe / révisable. |
| Prix du kWh – HP/HC × saison haute/basse | Prix complet TTC par plage. |
| Abonnement (an / mois / jour) | Abonnement TTC fourniture + acheminement. |
| Tarif en vigueur depuis | Date d'effet des prix, avec l'offre et la raison en attributs. |

L'**option « part de consommation en heures pleines »** (82 % par défaut) règle le capteur estimé.
Pour la calibrer : prix moyen de ta dernière facture ÷ kWh, comparé aux prix HP/HC de la saison.

Tableau Énergie : *Réseau électrique → Utiliser une entité avec le prix actuel* → `Prix du kWh (estimé…)`.
L'abonnement n'est pas géré par le tableau Énergie.

## Développement

```bash
pip install pytest
python -m pytest
```

Les tests utilisent une réponse réelle (identifiants de contrat anonymisés) dans `tests/fixtures/`.
