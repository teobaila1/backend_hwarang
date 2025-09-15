from flask import Flask
from flask_cors import CORS
from backend.accounts.autentificare import autentificare_bp
from backend.users.antrenori_externi import antrenori_externi_bp
from backend.users.antrenor_dashboard_copii_parinti import antrenor_dashboard_copii_parinti_bp
from backend.competitions.adauga_concurs import adauga_concurs_bp
from backend.mails.evidenta_plati import evidenta_plati_bp
from backend.competitions.numar_inscrisi import numar_inscrisi_bp
from backend.competitions.creare_get_concurs import creare_get_concurs_bp
from backend.users.toti_copiii_parintilor import toti_copiii_parintilor_bp
from backend.users.toate_grupele_antrenori import toate_grupele_antrenori_bp
from backend.competitions.inscrieri_concursuri_toti import inscriere_concurs_toti_bp
from backend.competitions.concurs_permis_antrenori_externi import concurs_permis_antrenori_externi_bp
from backend.document.upload_document import upload_document_bp
from backend.competitions.inscriere_concurs import inscriere_concurs_bp
from backend.users.toti_userii import toti_userii_bp
from backend.accounts.inregistrare import inregistrare_bp
from backend.accounts.inscriere import inscriere_bp
from backend.users.cereri_utilizatori import cereri_utilizatori_bp
from backend.mails.modifica_rol import modifica_rol_bp
from backend.competitions.stergere_concurs import stergere_concurs_bp
from backend.passwords.resetare_parola import resetare_bp
from backend.users.parinti import parinti_bp
from backend.users.elevi import elevi_bp

app = Flask(__name__)
CORS(app)

app.register_blueprint(inscriere_bp)
app.register_blueprint(autentificare_bp)
app.register_blueprint(inregistrare_bp)
app.register_blueprint(cereri_utilizatori_bp)
app.register_blueprint(toti_userii_bp)
app.register_blueprint(modifica_rol_bp)
app.register_blueprint(inscriere_concurs_bp)
app.register_blueprint(upload_document_bp)
app.register_blueprint(antrenori_externi_bp)
app.register_blueprint(concurs_permis_antrenori_externi_bp)
app.register_blueprint(antrenor_dashboard_copii_parinti_bp)
app.register_blueprint(inscriere_concurs_toti_bp)
app.register_blueprint(toate_grupele_antrenori_bp)
app.register_blueprint(toti_copiii_parintilor_bp)
app.register_blueprint(adauga_concurs_bp)
app.register_blueprint(creare_get_concurs_bp)
app.register_blueprint(numar_inscrisi_bp)
app.register_blueprint(evidenta_plati_bp)
app.register_blueprint(stergere_concurs_bp)
app.register_blueprint(resetare_bp)
app.register_blueprint(parinti_bp)
app.register_blueprint(elevi_bp)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
