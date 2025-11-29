from django.shortcuts import render

# Create your views here.

# Home landing page
def index(request):
    return render(request, 'wildlife/index.html')