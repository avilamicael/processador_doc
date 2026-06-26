// Dados mock do design DocWatch (Opção B). Substituir por dados da API nas fases GSD.
// Fase 2 (02-05): DOCS/FOLDERS/STATUS_LABELS removidos — Documentos e Pastas usam
// dados reais via TanStack Query (src/hooks/*). Os arrays abaixo pertencem a telas
// de fases futuras (Templates/Automações/Integrações/Regras) ainda não fiadas.
// TEMPLATES mock removido na Fase 4 (04-06): a TemplatesPage agora lê templates
// reais via TanStack Query (useTemplates) — o tipo Template passou a refletir a API.
import type { Integration, Rule } from '../types'

export const RULES: Rule[] = [
  { id: 1, name: 'Por marcador QR Code', param: 'SEP-DOC', desc: 'Cria um novo documento sempre que encontra um QR Code de separação na página.' },
  { id: 2, name: 'Por número de páginas', param: 'a cada 1 pág.', desc: 'Cria um novo documento a cada N páginas do PDF de origem.' },
  { id: 3, name: 'Por palavra-chave', param: '“CONTRATO”', desc: 'Inicia um novo documento ao encontrar uma palavra-chave no topo da página.' },
  { id: 4, name: 'Por página em branco', param: 'sensibilidade 98%', desc: 'Usa páginas em branco como separadores entre documentos.' },
]

export const INTEGRATIONS: Integration[] = [
  { id: 1, name: 'Google Drive', cat: 'Armazenamento', mono: 'GD', on: true },
  { id: 3, name: 'Amazon S3', cat: 'Armazenamento', mono: 'S3', on: false },
  { id: 5, name: 'Webhook', cat: 'Integração', mono: '{}', on: true },
  { id: 6, name: 'E-mail (SMTP)', cat: 'Notificação', mono: '@', on: true },
]
