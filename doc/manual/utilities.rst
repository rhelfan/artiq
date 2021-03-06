Utilities
=========

Local running tool
------------------

.. argparse::
   :ref: artiq.frontend.artiq_run.get_argparser
   :prog: artiq_run

Remote Procedure Call tool
------------------------------

.. argparse::
   :ref: artiq.frontend.artiq_rpctool.get_argparser
   :prog: artiq_rpctool

This tool is the preferred way of handling simple ARTIQ controllers.
Instead of writing a client for very simple cases you can just use this tool
in order to call remote functions of an ARTIQ controller.

* Listing existing targets

        The ``list-targets`` sub-command will print to standard output the
        target list of the remote server::

            $ artiq_rpctool.py hostname port list-targets

* Listing callable functions

        The ``list-methods`` sub-command will print to standard output a sorted
        list of the functions you can call on the remote server's target.

        The list will contain function names, signatures (arguments) and
        docstrings.

        If the server has only one target, you can do::

            $ artiq_rpctool.py hostname port list-methods

        Otherwise you need to specify the target, using the ``-t target``
        option::

            $ artiq_rpctool.py hostname port list-methods -t target_name

* Remotely calling a function

        The ``call`` sub-command will call a function on the specified remote
        server's target, passing the specified arguments.
        Like with the previous sub-command, you only need to provide the target
        name (with ``-t target``) if the server hosts several targets.

        The following example will call the ``set_attenuation`` method of the
        Lda controller with the argument ``5``::

            $ artiq_rpctool.py ::1 3253 call -t lda set_attenuation 5

        In general, to call a function named ``f`` with N arguments named
        respectively ``x1, x2, ..., xN`` you can do::

            $ artiq_rpctool.py hostname port call -t target f x1 x2 ... xN

        You can use Python syntax to compute arguments as they will be passed
        to the ``eval()`` primitive. But beware to use quotes to separate
        arguments which use spaces::

            $ artiq_rpctool.py hostname port call -t target f '3 * 4 + 2' True '[1, 2]'

        If the called function has a return value, it will get printed to
        the standard output if the value is not None like in the standard
        python interactive console::

            $ artiq_rpctool.py ::1 3253 call get_attenuation
            5.0 dB
