---
title: "Debugging a pod: mixed-language fixture"
date: 2026-01-01
draft: true
language: mixed
---

عند فشل الـ pod في Kubernetes، ابدأ بتشغيل `kubectl get pods` ثم راجع حالة الحاوية، (وليس السجلات فقط).

When a pod keeps restarting, check the events first: كيف تبدأ التشخيص؟ then read the container logs.

## تشخيص المشكلة

### Reading the events {.anchor-test}

- اقرأ الأحداث مع kubectl describe pod أولا.
- Check the restart count, ثم السجلات.
- Compare the image tag with the deployed one.
  - تحقق من وسم الصورة
  - Check the digest

> الحل الأسرع غالبا هو قراءة الأحداث قبل أي شيء آخر.
>
> > Nested quote: read the events first.

```bash
kubectl get pods -n demo
kubectl logs demo-pod --previous
```

- English first item, then Arabic below.
- عنصر عربي في قائمة تبدأ بالإنجليزية.
- [ ] A task-list item in English
