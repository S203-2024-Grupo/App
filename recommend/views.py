from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from .forms import *
from django.http import Http404, JsonResponse
from .models import Movie, Myrating, MyList
from django.db.models import Q, Case, When
from django.contrib import messages
from django.http import HttpResponseRedirect
import pandas as pd

def index(request):
    movies = Movie.objects.all()
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/list.html', {'movies': movies})

    return render(request, 'recommend/list.html', {'movies': movies})

def indexgenre(request):
    movies = Movie.objects.all().order_by('genre')
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct().order_by('genre')
        return render(request, 'recommend/list.html', {'movies': movies})

    return render(request, 'recommend/list.html', {'movies': movies})

# Show details of the movie
def detail(request, movie_id):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404
    movies = get_object_or_404(Movie, id=movie_id)
    movie = Movie.objects.get(id=movie_id)

    temp = list(MyList.objects.all().values().filter(movie_id=movie_id, user=request.user))
    if temp:
        update = temp[0]['watch']
    else:
        update = False
    if request.method == "POST":

        # For my list
        if 'watch' in request.POST:
            watch_flag = request.POST['watch']
            if watch_flag == 'on':
                update = True
            else:
                update = False
            if MyList.objects.all().values().filter(movie_id=movie_id, user=request.user):
                MyList.objects.all().values().filter(movie_id=movie_id, user=request.user).update(watch=update)
            else:
                q = MyList(user=request.user, movie=movie, watch=update)
                q.save()
            if update:
                messages.success(request, "Movie added to your list!")
            else:
                messages.success(request, "Movie removed from your list!")

        # For rating
        else:
            rate = request.POST['rating']
            if Myrating.objects.all().values().filter(movie_id=movie_id, user=request.user):
                Myrating.objects.all().values().filter(movie_id=movie_id, user=request.user).update(rating=rate)
            else:
                q = Myrating(user=request.user, movie=movie, rating=rate)
                q.save()

            messages.success(request, "Rating has been submitted!")

        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    out = list(Myrating.objects.filter(user=request.user.id).values())

    # To display ratings in the movie detail page
    movie_rating = 0
    rate_flag = False
    for each in out:
        if each['movie_id'] == movie_id:
            movie_rating = each['rating']
            rate_flag = True
            break

    context = {'movies': movies, 'movie_rating': movie_rating, 'rate_flag': rate_flag, 'update': update}
    return render(request, 'recommend/detail.html', context)

# MyList functionality
def watch(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movies = Movie.objects.filter(mylist__watch=True, mylist__user=request.user)
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/watch.html', {'movies': movies})

    return render(request, 'recommend/watch.html', {'movies': movies})

# To get similar movies based on user rating
def get_similar(movie_name, rating, corrMatrix):
    similar_ratings = corrMatrix[movie_name] * (rating - 2.5)
    similar_ratings = similar_ratings.sort_values(ascending=False)
    return similar_ratings

# Recommendation Algorithm
def recommend(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movie_rating = pd.DataFrame(list(Myrating.objects.all().values()))
    userRatings = movie_rating.pivot_table(index=['user_id'], columns=['movie_id'], values='rating')
    userRatings = userRatings.fillna(0, axis=1)
    corrMatrix = userRatings.corr(method='pearson')

    user = pd.DataFrame(list(Myrating.objects.filter(user=request.user).values())).drop(['user_id', 'id'], axis=1)
    user_filtered = [tuple(x) for x in user.values]
    movie_id_watched = [each[0] for each in user_filtered]

    similar_ratings = pd.Series()
    for movie, rating in user_filtered:
        if not similar_ratings.empty:
            similar_ratings += get_similar(movie, rating, corrMatrix)
        else:
            similar_ratings = get_similar(movie, rating, corrMatrix)

    movies_id = list(similar_ratings.groupby('movie_id').sum().sort_values(ascending=False).index)
    movies_id_recommend = [each for each in movies_id if each not in movie_id_watched]
    preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(movies_id_recommend)])
    movie_list = list(Movie.objects.filter(id__in=movies_id_recommend).order_by(preserved)[:10])

    context = {'movie_list': movie_list}
    return render(request, 'recommend/recommend.html', context)

# Nova view para exportar recomendações em formato JSON
def recommend_json(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'User not authenticated'}, status=401)
    if not request.user.is_active:
        return JsonResponse({'error': 'User not active'}, status=403)

    movie_rating = pd.DataFrame(list(Myrating.objects.all().values()))
    userRatings = movie_rating.pivot_table(index=['user_id'], columns=['movie_id'], values='rating')
    userRatings = userRatings.fillna(0, axis=1)
    corrMatrix = userRatings.corr(method='pearson')

    user = pd.DataFrame(list(Myrating.objects.filter(user=request.user).values())).drop(['user_id', 'id'], axis=1)
    user_filtered = [tuple(x) for x in user.values]
    movie_id_watched = [each[0] for each in user_filtered]

    similar_ratings = pd.Series(dtype=float)
    for movie, rating in user_filtered:
        if not similar_ratings.empty:
            similar_ratings += get_similar(movie, rating, corrMatrix)
        else:
            similar_ratings = get_similar(movie, rating, corrMatrix)

    movies_id = list(similar_ratings.groupby('movie_id').sum().sort_values(ascending=False).index)
    movies_id_recommend = [each for each in movies_id if each not in movie_id_watched]
    preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(movies_id_recommend)])
    movie_list = list(Movie.objects.filter(id__in=movies_id_recommend).order_by(preserved)[:10])

    recommendations = [{'id': movie.id, 'title': movie.title} for movie in movie_list]

    return JsonResponse(recommendations, safe=False)

# Register user
def signUp(request):
    form = UserForm(request.POST or None)

    if form.is_valid():
        user = form.save(commit=False)
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user.set_password(password)
        user.save()
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")

    context = {'form': form}

    return render(request, 'registration/signUp.html', context)

# Login User
def Login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")
            else:
                return render(request, 'registration/login.html', {'error_message': 'Your account disable'})
        else:
            return render(request, 'registration/login.html', {'error_message': 'Invalid Login'})

    return render(request, 'registration/login.html')

# Logout user
def Logout(request):
    logout(request)
    return redirect("login")

def listUsers(request):
    users = User.objects.all()
    return render(request, 'recommend/list_users.html', {'users': users})
