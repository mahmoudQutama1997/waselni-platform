# تجهيز WASELNI للرفع على GitHub

## البنية المعتمدة

هذا المشروع **Monorepo**: مستودع GitHub رئيسي واحد يضم الواجهات الأربع والخادم المشترك. لا تنشئ أربعة مستودعات منفصلة من هذا المصدر حالياً؛ لأن الواجهات الأربع مبنية من مصدر React مشترك وتعتمد على Django API وقاعدة بيانات واحدة. يمكن نشر كل واجهة بشكل مستقل من نفس المستودع.

```text
waselni/
├── backend/                 # Django REST API + قاعدة البيانات + WebSockets
├── frontend/                # React/Vite source مشترك
│   ├── src/customer/        # تجربة الزبون ومكوناتها
│   ├── native/customer/     # إعداد تطبيق الزبون (Capacitor)
│   ├── native/captain/      # إعداد تطبيق الكابتن (Capacitor)
│   └── native/merchant/     # إعداد تطبيق التاجر (Capacitor)
├── .github/workflows/       # فحوصات تلقائية عند Push و Pull Request
├── ARCHITECTURE_SPLIT_PLAN.md
└── README.md
```

## الواجهات الأربعة

من مجلد `frontend`، كل أمر ينتج نسخة مستقلة في `dist`:

| الواجهة | أمر البناء | مجلد الناتج |
|---|---|---|
| الزبون | `npm run build:customer` | `frontend/dist/customer` |
| الكابتن | `npm run build:captain` | `frontend/dist/captain` |
| التاجر | `npm run build:merchant` | `frontend/dist/merchant` |
| الإدارة | `npm run build:admin` | `frontend/dist/admin` |

لبناء الجميع: `npm run build:all-portals`.

هذه أربعة أهداف بناء ونشر منفصلة، وليست أربعة قواعد بيانات أو أربعة Backends. يجب أن تشير جميعها إلى عنوان API المركزي نفسه.

## إنشاء مستودع GitHub ورفع المشروع (Windows PowerShell)

1. أنشئ مستودعاً جديداً باسم `waselni-platform` على GitHub، ويفضّل أن يكون **Private** أثناء التطوير. لا تختر إنشاء README أو `.gitignore` أو License من GitHub لأن هذه الملفات موجودة في المشروع.
2. فك ضغط حزمة المشروع، وافتح PowerShell داخل مجلد `waselni` الذي يحتوي على `backend` و`frontend`.
3. نفّذ الأوامر التالية، واستبدل الرابط برابط المستودع الذي أنشأته أنت:

```powershell
git init
git add .
git status
git commit -m "Prepare WASELNI monorepo for GitHub"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/waselni-platform.git
git push -u origin main
```

راجع ناتج `git status` قبل `git commit`. يجب ألا يظهر أي ملف `.env` حقيقي أو قاعدة بيانات أو ملفات `node_modules`. ملفات `.env.example` و`.env.*.example` فقط مسموح رفعها.

## تشغيل الفحوصات محلياً

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

### Frontend

```powershell
cd ..\frontend
npm ci
npm run build:all-portals
```

## نشر الواجهات بشكل منفصل

أنشئ أربعة إعدادات نشر مرتبطة بالمستودع نفسه، وحدد لكل إعداد أمر البناء ومجلد الناتج الواردين في الجدول أعلاه. عيّن `VITE_API_URL` في إعدادات البناء ليشير إلى الخادم المركزي، مثال: `https://api.example.com/api`. لا تستخدم `localhost` أو عنوان شبكة محلية في تطبيقات الإنتاج.

الخادم المركزي يحتاج إعدادات مستقلة: `SECRET_KEY` قوي وسري، `DEBUG=False`، `ALLOWED_HOSTS`، `CORS_ALLOWED_ORIGINS`، `CSRF_TRUSTED_ORIGINS`، و`DATABASE_URL`. ضع القيم السرية في GitHub Secrets أو إعدادات الاستضافة، ولا تضعها في المستودع.

## قواعد أمان مهمة

- لا ترفع ملفات `.env` الحقيقية، كلمات المرور، مفاتيح API، رموز JWT، قواعد البيانات، أو ملفات الوسائط الخاصة بالمستخدمين.
- لا ترفع `node_modules` أو مجلدات البيئة الافتراضية. تثبيت الحزم يتم من `package-lock.json` و`requirements.txt`.
- لا تستخدم حسابات التجربة في الإنتاج. أمر `seed_demo` مخصص للتطوير المحلي فقط ويتطلب `DEBUG=True` وكلمة مرور من متغير `WASELNI_DEMO_PASSWORD`.
- إنشاء حساب المدير الأول يتم من خلال مسار آمن على الخادم، ولا تضع بيانات المدير في GitHub.
- لا تعتبر المشروع جاهزاً للإنتاج بمجرد نجاح رفعه؛ راجع `PRODUCTION_READINESS_REPORT.md`، فهناك تكاملات تشغيلية تحتاج إعداداً واختبارات على بيئة مستضافة.

## ملاحظة عن الحالة الحالية

الحزمة التي جرى فحصها لا تحتوي على مشاريع Android/iOS المولّدة؛ الموجود هو إعدادات Capacitor. توليد وتشغيل تطبيق Android يحتاج Android Studio وAndroid SDK، أما iOS فيحتاج macOS وXcode. كما أن اختبار التكامل الكامل يحتاج Backend منشوراً وخدماته الخارجية مضبوطة.
