#include <cctype>
#include <iostream>
#include <sstream>
#include <string>

using namespace std;

int main()
{
    int a[100];
    int n, i, j;
    int count = 0;
    string line, elements;
    char extra;

    cout << "Введите количество элементов (от 1 до 100): ";
    getline(cin, line);
    istringstream size_input(line);
    if (!(size_input >> n) || (size_input >> extra) || n < 1 || n > 100) {
        cout << "Ошибка: введите одно целое число от 1 до 100 без лишних символов." << endl;
        return 1;
    }

    cout << "Введите " << n << " целых чисел в одной строке: ";
    getline(cin, elements);
    istringstream input(elements);
    for (int k = 0; k < n; k++) {
        if (!(input >> a[k]) || (!input.eof() && !isspace(input.peek()))) {
            cout << "Ошибка: введите ровно " << n << " целых чисел через пробел без лишних символов." << endl;
            return 1;
        }
    }
    if (input >> extra) {
        cout << "Ошибка: введите ровно " << n << " целых чисел через пробел без лишних символов." << endl;
        return 1;
    }

    i = 0;
    j = 1;
    while (i < n - 1) {
        if (a[i] < a[j]) {
            count++;
        }
        j++;
        if (j == n) {
            i++;
            j = i + 1;
        }
    }

    cout << "Количество пар: " << count << endl;
    return 0;
}
