import { TEMPLATES } from '../data/mock'
import { Icon } from '../components/Icon'

export function TemplatesPage() {
  return (
    <div>
      <div className="sec-head">
        <div className="sec-head-col">
          <h2 className="sec-title">Templates de documento</h2>
          <p className="sec-desc">Cada template define o tipo de documento e os campos extraídos pelo motor de leitura.</p>
        </div>
        <button className="btn-primary"><Icon name="plus" size={15} />Novo template</button>
      </div>

      <div className="tpl-grid">
        {TEMPLATES.map((t) => (
          <div key={t.name} className="card tpl-card">
            <div className="tpl-head">
              <div className="tpl-head-info">
                <div className="tpl-icon"><Icon name="grid" size={19} /></div>
                <div>
                  <div className="tpl-name">{t.name}</div>
                  <div className="tpl-type">{t.type}</div>
                </div>
              </div>
              <button className="row-action" title="Mais"><Icon name="dots" size={16} /></button>
            </div>

            <div className="tpl-fields-label">CAMPOS EXTRAÍDOS</div>
            <div className="tags">
              {t.fields.map((f) => (
                <span key={f} className="tag">{f}</span>
              ))}
            </div>

            <div className="tpl-foot">
              <span><Icon name="tableMini" size={13} />{t.docs} docs</span>
              <span><Icon name="checkSmall" size={13} />{t.rule}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
