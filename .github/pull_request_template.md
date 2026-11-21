## Qué cambia

<!-- Una o dos frases. -->

## Promoción

- [ ] `feature/*` → `dev`  ·  `dev` → `test`  ·  `test` → `prod` (lo verifica `promote-guard`)

## Checklist

- [ ] Pruebas nuevas o actualizadas (unit / integration / e2e según el cambio)
- [ ] Revisé el comentario de `terraform-plan`: no destruye nada inesperado
- [ ] Sin secretos ni credenciales reales en el diff
- [ ] Si toca el gateway: el canary decidirá promoción o rollback al fusionar
